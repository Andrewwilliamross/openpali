"""Building scene: the county 3D building model compiled into quantized,
individually addressable GPU batches, registered to a baked terrain pyramid.

    python -m openpali.scene.build     # fetch (cached), compile, write a scene
    python -m openpali.scene.verify    # check the current scene's integrity

The scene is a derived display artifact. It records what stood in the county's
2023 model; it makes no claim about present physical conditions.
"""
