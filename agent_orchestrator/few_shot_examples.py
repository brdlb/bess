FEW_SHOT_EXAMPLES = """
Here are some examples of correctly formatted hou module scripts.

EXAMPLE 1: Create a box
```python
obj = hou.node('/obj')
geo = obj.createNode('geo', 'my_box_geo')
box = geo.createNode('box')
result['message'] = f"Successfully created {geo.path()} and box inside."
```

EXAMPLE 2: Set parameters
```python
node = hou.node('/obj/my_box_geo/box1')
node.parm('sizex').set(2.0)
node.parm('sizey').set(3.5)
result['message'] = "Updated box dimensions."
```

EXAMPLE 3: Read attributes
```python
node = hou.node('/obj/my_box_geo/box1')
geo = node.geometry()
point_count = len(geo.points())
result['data'] = {"point_count": point_count}
```
"""
