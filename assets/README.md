# PuppyPi simulation assets

`puppypi_description/` contains the Hiwonder CAD meshes and partial Xacro files
already present in the project before repository initialization. The recorded
upstream is [Hiwonder/PuppyPi](https://github.com/Hiwonder/PuppyPi), branch `ros2`.
The exact upstream revision and asset license were not recorded in the original
handoff. Preserve the supplied files and recover this provenance before a public
asset distribution; no new license is assigned to them by this repository.

The Xacro snapshot references files that are not included. It is reference
material, not a complete installable ROS description package. The MuJoCo builder
uses the available STL meshes directly.

`mujoco_generated/` is ignored by Git. The renderer recreates its XML and textures
with paths valid for the current checkout:

```bash
make render-3d
```

The resulting animation is a scripted visualization. It does not establish
closed-loop locomotion, contact dynamics, or hardware success.
