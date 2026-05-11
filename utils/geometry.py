from typing import Tuple

Point = Tuple[int, int]

def ccw(A: Point, B: Point, C: Point) -> bool:
    """Check if three points are listed in a counterclockwise order."""
    return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

def intersect(A: Point, B: Point, C: Point, D: Point) -> bool:
    """
    Return true if line segments AB and CD intersect.
    A, B: Previous and current points of object centroid
    C, D: Points of the counting line
    """
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

def get_centroid(box: Tuple[int, int, int, int]) -> Point:
    """Calculate the centroid of a bounding box."""
    x1, y1, x2, y2 = box
    return int((x1 + x2) / 2), int((y1 + y2) / 2)
