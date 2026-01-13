import sys

path = "/Users/bennet/Desktop/temper/packages/temper-placer/src/temper_placer/optimizer/train.py"
with open(path, "r") as f:
    lines = f.readlines()

# Find the start and end of the corrupted block
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "Run training step" in line and 880 <= i <= 910:
        start_idx = i
    if "loss_value = float(loss)" in line and 920 <= i <= 960:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_block = [
        "            # Run training step (returns breakdown alongside loss to avoid recomputation)\n",
        "            (\n",
        "                new_positions,\n",
        "                new_rotation_logits,\n",
        "                new_side_logits,\n",
        "                new_net_virtual_nodes,\n",
        "                loss,\n",
        "                loss_breakdown_arrays,\n",
        "                new_opt_state_pos,\n",
        "                new_opt_state_rot,\n",
        "                new_opt_state_side,\n",
        "                new_opt_state_vn,\n",
        "                grad_pos,\n",
        "                grad_rot,\n",
        "                grad_side,\n",
        "                grad_vn,\n",
        "                new_ema,\n",
        "                new_loss_weights,\n",
        "                new_initial_grad_norms,\n",
        "            ) = train_step(\n",
        "                state.positions,\n",
        "                state.rotation_logits,\n",
        "                rotations,\n",
        "                state.side_logits,\n",
        "                sides,\n",
        "                state.net_virtual_nodes,\n",
        "                state.opt_state_pos,\n",
        "                state.opt_state_rot,\n",
        "                state.opt_state_side,\n",
        "                state.opt_state_vn,\n",
        "                epoch,\n",
        "                lr,\n",
        "                state.position_delta_ema,\n",
        "                state.overlap_weights,\n",
        "                state.loss_weights,\n",
        "                state.initial_grad_norms,\n",
        "            )\n",
        "\n",
        "            # Update state\n",
        "            state.positions = new_positions\n",
        "            state.rotation_logits = new_rotation_logits\n",
        "            state.side_logits = new_side_logits\n",
        "            state.net_virtual_nodes = new_net_virtual_nodes\n",
        "            state.opt_state_pos = new_opt_state_pos\n",
        "            state.opt_state_rot = new_opt_state_rot\n",
        "            state.opt_state_side = new_opt_state_side\n",
        "            state.opt_state_vn = new_opt_state_vn\n",
        "            state.position_delta_ema = float(new_ema)\n",
        "            state.loss_weights = new_loss_weights\n",
        "            state.initial_grad_norms = new_initial_grad_norms\n",
        "\n",
        "            # --- Convergence Tracking ---\n"
    ]
    lines[start_idx:end_idx] = new_block
    with open(path, "w") as f:
        f.writelines(lines)
    print("Fixed corrupted block.")
else:
    print(f"Failed to find block: start={start_idx}, end={end_idx}")
