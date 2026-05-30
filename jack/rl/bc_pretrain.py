"""Behavioural cloning from DeterministicSolver demonstrations.

Pipeline:
  1. Collect (obs, action, mask) tuples from the solver playing N games.
  2. Train the PPO policy network with masked cross-entropy to imitate.
  3. Save a MaskablePPO checkpoint that train.py can --resume from.

Usage:
    python -m jack.rl.bc_pretrain --games 5000 --epochs 20
    python -m jack.rl.bc_pretrain --games 5000 --epochs 20 --output jack/rl/checkpoints/bc_init.zip
    python -m jack.rl.bc_pretrain --games 5000 --epochs 20 --resume jack/rl/checkpoints/ckpt_004100008.zip
"""
import argparse
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from jack.rl.env import BingoEnv
from jack.rl.train import BingoExtractor  # noqa: F401 — registers custom class


DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), 'checkpoints', 'bc_init.zip')


# ── Demo collection ────────────────────────────────────────────────────────────

def collect_demos(n_games: int = 5000, verbose: bool = True):
    """Run solver as player 0 for n_games and return (obs, action, mask) arrays."""
    from jack.solver.det_solver import DeterministicSolver

    solver  = DeterministicSolver()
    obs_list, act_list, mask_list = [], [], []

    t0 = time.time()
    for game_idx in range(n_games):
        env  = BingoEnv(board_seed=game_idx)
        obs, _ = env.reset(seed=game_idx)
        done = False

        while not done:
            mask   = env.action_masks()
            action = solver.act(env.game, 0, mask)

            obs_list.append(obs.copy())
            act_list.append(action)
            mask_list.append(mask.copy())

            obs, _, terminated, truncated, _ = env.step(action)
            done = terminated or truncated

        if verbose and (game_idx + 1) % 500 == 0:
            elapsed = time.time() - t0
            steps   = len(obs_list)
            print(f"  Collected {game_idx + 1}/{n_games} games  "
                  f"({steps:,} steps, {elapsed:.0f}s)")

    obs_arr  = np.array(obs_list,  dtype=np.float32)
    act_arr  = np.array(act_list,  dtype=np.int64)
    mask_arr = np.array(mask_list, dtype=bool)

    if verbose:
        print(f"  Total: {len(obs_arr):,} (obs, action, mask) tuples "
              f"from {n_games} games in {time.time()-t0:.0f}s")

    return obs_arr, act_arr, mask_arr


# ── BC training ────────────────────────────────────────────────────────────────

def bc_train(
    model,
    obs_arr:   np.ndarray,
    act_arr:   np.ndarray,
    mask_arr:  np.ndarray,
    n_epochs:  int   = 20,
    batch_size: int  = 512,
    lr:        float = 1e-3,
    device:    str   = 'auto',
    verbose:   bool  = True,
):
    """Supervised-train model.policy to imitate (obs → action) pairs.

    Uses masked cross-entropy: invalid actions are set to -inf before softmax
    so the policy only learns to choose among valid moves.
    """
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'

    policy = model.policy.to(device)
    policy.set_training_mode(True)

    optimizer = torch.optim.Adam(policy.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)

    obs_t  = torch.tensor(obs_arr,            device=device)
    act_t  = torch.tensor(act_arr,            device=device)
    mask_t = torch.tensor(mask_arr.astype(np.float32), device=device)  # 1=valid, 0=invalid

    dataset = TensorDataset(obs_t, act_t, mask_t)
    loader  = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    best_loss = float('inf')
    best_state = None

    for epoch in range(n_epochs):
        total_loss = 0.0
        total_acc  = 0
        n_batches  = 0

        for obs_b, act_b, mask_b in loader:
            # Forward pass through feature extractor + actor head
            with torch.no_grad():
                features = policy.extract_features(obs_b, policy.features_extractor)
            latent_pi, _ = policy.mlp_extractor(features)
            logits = policy.action_net(latent_pi)           # (B, UNIVERSE_SIZE)

            # Mask invalid actions to -inf
            logits = logits + (mask_b - 1) * 1e9           # invalid → logits - 1e9

            loss = F.cross_entropy(logits, act_b)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()
            total_acc  += (logits.argmax(dim=1) == act_b).float().mean().item()
            n_batches  += 1

        scheduler.step()
        avg_loss = total_loss / n_batches
        avg_acc  = total_acc  / n_batches

        if avg_loss < best_loss:
            best_loss  = avg_loss
            best_state = {k: v.cpu().clone() for k, v in policy.state_dict().items()}

        if verbose:
            print(f"  Epoch {epoch+1:>3}/{n_epochs}  loss={avg_loss:.4f}  "
                  f"acc={avg_acc:.1%}  lr={scheduler.get_last_lr()[0]:.2e}")

    # Restore best weights
    if best_state is not None:
        policy.load_state_dict(best_state)

    policy.set_training_mode(False)
    if verbose:
        print(f"  Best loss: {best_loss:.4f}")


# ── Full pipeline ──────────────────────────────────────────────────────────────

def run(
    n_games:    int   = 5000,
    n_epochs:   int   = 20,
    batch_size: int   = 512,
    lr:         float = 1e-3,
    output:     str   = DEFAULT_OUTPUT,
    resume:     str   = None,
    verbose:    bool  = True,
):
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.env_util import make_vec_env
    from stable_baselines3.common.vec_env  import VecNormalize

    print("=" * 60)
    print("Behavioural Cloning — DeterministicSolver → PPO policy")
    print("=" * 60)

    # ── Step 1: collect demos ──────────────────────────────────────────────────
    print(f"\n[1/3] Collecting {n_games} solver games...")
    obs_arr, act_arr, mask_arr = collect_demos(n_games, verbose=verbose)

    # ── Step 2: build / load model ─────────────────────────────────────────────
    print(f"\n[2/3] Setting up model...")
    vec_env = VecNormalize(
        make_vec_env(BingoEnv, n_envs=1),
        norm_obs=False, norm_reward=True, clip_reward=10.0,
    )

    if resume and os.path.exists(resume):
        print(f"  Resuming policy weights from {resume}")
        model = MaskablePPO.load(resume, env=vec_env)
    else:
        model = MaskablePPO(
            policy="MlpPolicy",
            env=vec_env,
            verbose=0,
            policy_kwargs=dict(
                features_extractor_class=BingoExtractor,
                features_extractor_kwargs=dict(features_dim=256),
                net_arch=dict(pi=[256], vf=[256]),
            ),
        )
        print("  Fresh model initialised")

    # ── Step 3: BC training ────────────────────────────────────────────────────
    print(f"\n[3/3] BC training — {n_epochs} epochs, batch={batch_size}, lr={lr}")
    bc_train(model, obs_arr, act_arr, mask_arr,
             n_epochs=n_epochs, batch_size=batch_size, lr=lr, verbose=verbose)

    # ── Save ───────────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    save_path = output.replace('.zip', '')
    model.save(save_path)
    print(f"\nSaved BC model to {save_path}.zip")
    print("Resume PPO training with:")
    print(f"  python -m jack.rl.train --timesteps 5000000 "
          f"--resume {save_path}.zip --solver-opp 0.2 "
          f"--log jack/rl/logs/train_v17_bc.log")
    return model


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Behavioural cloning from DeterministicSolver')
    parser.add_argument('--games',      type=int,   default=5000,
                        help='Number of solver games to collect (default 5000)')
    parser.add_argument('--epochs',     type=int,   default=20,
                        help='BC training epochs (default 20)')
    parser.add_argument('--batch-size', type=int,   default=512)
    parser.add_argument('--lr',         type=float, default=1e-3)
    parser.add_argument('--output',     type=str,   default=DEFAULT_OUTPUT,
                        help='Output checkpoint path (default: checkpoints/bc_init.zip)')
    parser.add_argument('--resume',     type=str,   default=None,
                        help='Warm-start from an existing PPO checkpoint before BC')
    args = parser.parse_args()

    run(
        n_games=args.games,
        n_epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        output=args.output,
        resume=args.resume,
    )
