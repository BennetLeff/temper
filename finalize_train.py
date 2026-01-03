import sys

path = "/Users/bennet/Desktop/temper/packages/temper-placer/src/temper_placer/optimizer/train.py"
with open(path, "r") as f:
    text = f.read()

# 1. Update Tracking best block
# Be careful with whitespace - match exactly what's in the file
# 12 spaces then "if loss_value..."
# Actually I'll use a more robust replacement if possible, but let's try this.

old_track = """            if loss_value < best_loss - config.early_stopping.min_delta:
                best_loss = loss_value
                best_positions = state.positions
                best_rotations = rotations
                epochs_without_improvement = 0"""
new_track = """            if loss_value < best_loss - config.early_stopping.min_delta:
                best_loss = loss_value
                best_positions = state.positions
                best_rotations = rotations
                best_sides = sides
                epochs_without_improvement = 0"""
if old_track in text:
    text = text.replace(old_track, new_track)
    print("Updated track best block.")
else:
    print("Failed to find track best block.")

# 2. Update final_state
old_final = """    final_state = PlacementState(
        positions=state.positions,
        rotation_logits=state.rotation_logits,
    )"""
new_final = """    final_state = PlacementState(
        positions=state.positions,
        rotation_logits=state.rotation_logits,
        side_logits=state.side_logits,
    )"""
if old_final in text:
    text = text.replace(old_final, new_final)
    print("Updated final_state block.")
else:
    print("Failed to find final_state block.")

# 3. Update best_state
old_best = """    best_rotation_logits = jnp.where(
        best_rotations > 0.5,
        jnp.ones_like(best_rotations) * 5.0,  # High logit for selected
        jnp.zeros_like(best_rotations),  # Zero for others
    )
    best_state = PlacementState(
        positions=best_positions,
        rotation_logits=best_rotation_logits,
    )"""
new_best = """    best_rotation_logits = jnp.where(
        best_rotations > 0.5,
        jnp.ones_like(best_rotations) * 5.0,  # High logit for selected
        jnp.zeros_like(best_rotations),  # Zero for others
    )
    best_side_logits = jnp.where(
        best_sides > 0.5,
        jnp.ones_like(best_sides) * 5.0,
        jnp.zeros_like(best_sides),
    )
    best_state = PlacementState(
        positions=best_positions,
        rotation_logits=best_rotation_logits,
        side_logits=best_side_logits,
    )"""
if old_best in text:
    text = text.replace(old_best, new_best)
    print("Updated best_state block.")
else:
    print("Failed to find best_state block.")

with open(path, "w") as f:
    f.write(text)
