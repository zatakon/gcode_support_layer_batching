"""Collision detection for nozzle geometry vs. printed parts.

This module analyzes whether a nozzle can safely print multiple consecutive
layers without colliding with already-printed geometry.
"""

import numpy as np
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass
from gcode_parser import Layer, GCodeCommand


@dataclass
class NozzleGeometry:
    """Represents the geometry of a 3D printer nozzle."""
    diameter: float  # Nozzle tip diameter in mm
    cone_angle: float = 60.0  # Cone angle in degrees (from image: E3D v6 = 60°)
    height: float = 10.0  # Height of the conical section in mm
    
    def get_radius_at_height(self, height: float) -> float:
        """Calculate nozzle radius at a given height above the tip."""
        if height <= 0:
            return self.diameter / 2
        
        # Calculate radius based on cone angle
        # tan(angle/2) = radius_increase / height
        angle_rad = np.radians(self.cone_angle / 2)
        radius = (self.diameter / 2) + height * np.tan(angle_rad)
        return radius


class CollisionDetector:
    """Detects potential collisions between nozzle and printed geometry."""
    
    def __init__(self, nozzle: NozzleGeometry, safety_margin: float = 1.0):
        """
        Initialize collision detector.
        
        Args:
            nozzle: Nozzle geometry specification
            safety_margin: Additional safety margin in mm
        """
        self.nozzle = nozzle
        self.safety_margin = safety_margin
        self.layer_geometry: dict[int, Set[Tuple[int, int]]] = {}  # Voxel grid per layer
        self.voxel_size = 0.5  # mm per voxel
    
    def build_geometry_map(self, layers: List[Layer]) -> None:
        """Build a spatial map of all printed geometry."""
        self.layer_geometry.clear()
        
        for layer in layers:
            voxels = set()
            
            for cmd in layer.commands:
                # Only consider extrusion moves (E > 0 in relative mode)
                if cmd.x is not None and cmd.y is not None and cmd.e is not None:
                    if cmd.e > 0:  # Extrusion happening
                        voxel = self._position_to_voxel(cmd.x, cmd.y)
                        voxels.add(voxel)
            
            self.layer_geometry[layer.layer_number] = voxels
    
    def _position_to_voxel(self, x: float, y: float) -> Tuple[int, int]:
        """Convert XY position to voxel grid coordinates."""
        vx = int(x / self.voxel_size)
        vy = int(y / self.voxel_size)
        return (vx, vy)
    
    def can_batch_layers(self, start_layer: Layer, end_layer: Layer, 
                        all_layers: List[Layer]) -> bool:
        """Check if layers can be safely batched together.
        
        Args:
            start_layer: First layer in the batch
            end_layer: Last layer in the batch
            all_layers: All layers in the print
            
        Returns:
            True if batching is safe (no collisions)
        """
        # Calculate height difference
        z_diff = end_layer.z_height - start_layer.z_height
        
        # Check nozzle radius at this height
        nozzle_radius = self.nozzle.get_radius_at_height(z_diff)
        check_radius = nozzle_radius + self.safety_margin
        
        # Get geometry from intermediate layers (already printed)
        for layer in all_layers:
            if start_layer.layer_number < layer.layer_number < end_layer.layer_number:
                # Check if any geometry in this layer would collide
                if self._check_layer_collision(end_layer, layer, check_radius):
                    return False
        
        return True
    
    def _check_layer_collision(self, printing_layer: Layer, 
                              existing_layer: Layer, 
                              check_radius: float) -> bool:
        """Check if printing a layer would collide with existing geometry.
        
        Args:
            printing_layer: Layer being printed
            existing_layer: Already printed layer
            check_radius: Collision check radius in mm
            
        Returns:
            True if collision detected
        """
        if printing_layer.layer_number not in self.layer_geometry:
            return False
        if existing_layer.layer_number not in self.layer_geometry:
            return False
        
        printing_voxels = self.layer_geometry[printing_layer.layer_number]
        existing_voxels = self.layer_geometry[existing_layer.layer_number]
        
        # Check if any printing path comes too close to existing geometry
        check_voxel_radius = int(check_radius / self.voxel_size) + 1
        
        for px, py in printing_voxels:
            # Check neighborhood around each printing voxel
            for dx in range(-check_voxel_radius, check_voxel_radius + 1):
                for dy in range(-check_voxel_radius, check_voxel_radius + 1):
                    check_voxel = (px + dx, py + dy)
                    if check_voxel in existing_voxels:
                        # Calculate actual distance
                        distance = np.sqrt(dx**2 + dy**2) * self.voxel_size
                        if distance <= check_radius:
                            return True  # Collision detected
        
        return False
    
    def find_maximum_batch_size(self, start_layer: Layer, 
                                all_layers: List[Layer],
                                max_layers: int = 10) -> int:
        """Find the maximum number of consecutive layers that can be batched.
        
        Args:
            start_layer: First layer to start batching from
            all_layers: All layers in the print
            max_layers: Maximum layers to consider for batching
            
        Returns:
            Number of layers that can be safely batched
        """
        start_idx = start_layer.layer_number - 1
        batch_size = 1
        
        for i in range(1, max_layers + 1):
            next_idx = start_idx + i
            if next_idx >= len(all_layers):
                break
            
            next_layer = all_layers[next_idx]
            
            # Check if tools match
            if next_layer.tool != start_layer.tool:
                break
            
            # Check collision
            if not self.can_batch_layers(start_layer, next_layer, all_layers):
                break
            
            batch_size = i + 1
        
        return batch_size
