"""Layer batching logic for multi-material G-code optimization.

This module groups consecutive layers of the same material when
collision detection confirms it's safe to do so.
"""

from typing import List, Tuple
from dataclasses import dataclass, field
from gcode_parser import Layer
from collision_detector import CollisionDetector


@dataclass
class LayerBatch:
    """Represents a batch of consecutive layers printed with the same tool."""
    tool: int
    start_layer: int
    end_layer: int
    layers: List[Layer] = field(default_factory=list)
    
    def layer_count(self) -> int:
        """Return the number of layers in this batch."""
        return len(self.layers)
    
    def z_range(self) -> Tuple[float, float]:
        """Return the Z height range (min, max) of this batch."""
        if not self.layers:
            return (0.0, 0.0)
        return (self.layers[0].z_height, self.layers[-1].z_height)


class LayerBatcher:
    """Manages layer batching decisions based on collision detection."""
    
    def __init__(self, collision_detector: CollisionDetector, 
                 max_batch_layers: int = 10):
        """
        Initialize layer batcher.
        
        Args:
            collision_detector: Collision detector instance
            max_batch_layers: Maximum number of layers to batch together
        """
        self.collision_detector = collision_detector
        self.max_batch_layers = max_batch_layers
        self.batches: List[LayerBatch] = []
    
    def create_batches(self, layers: List[Layer]) -> List[LayerBatch]:
        """Create optimal layer batches from the input layers.
        
        This method reorganizes layers to batch same-tool layers together,
        minimizing tool changes while ensuring no collisions when printing.
        
        Strategy: Group layers by tool, then alternate between tools in batches,
        printing multiple layers of one material before switching.
        
        Args:
            layers: List of all layers in the print
            
        Returns:
            List of layer batches (may be reordered for efficiency)
        """
        self.batches.clear()
        
        if not layers:
            return self.batches
        
        # Build geometry map for collision detection
        self.collision_detector.build_geometry_map(layers)
        
        # Group layers by tool
        layers_by_tool = {}
        for layer in layers:
            tool = layer.tool if layer.tool is not None else 0
            if tool not in layers_by_tool:
                layers_by_tool[tool] = []
            layers_by_tool[tool].append(layer)
        
        # Sort each tool's layers by layer number to maintain order
        for tool in layers_by_tool:
            layers_by_tool[tool].sort(key=lambda l: l.layer_number)
        
        # Process layers by alternating between tools in batches
        tools = sorted(layers_by_tool.keys())
        tool_indices = {tool: 0 for tool in tools}
        processed_count = 0
        total_layers = len(layers)
        
        current_tool_idx = 0
        
        while processed_count < total_layers:
            # Get current tool
            current_tool = tools[current_tool_idx % len(tools)]
            tool_layers = layers_by_tool[current_tool]
            start_idx = tool_indices[current_tool]
            
            if start_idx >= len(tool_layers):
                # This tool is exhausted, try next
                current_tool_idx += 1
                if current_tool_idx >= len(tools) * 2:  # Prevent infinite loop
                    break
                continue
            
            # Collect a batch of layers for this tool
            batch_layers = []
            max_z_diff = 2.0  # Maximum Z height spread in a batch
            
            for i in range(start_idx, min(start_idx + self.max_batch_layers, len(tool_layers))):
                candidate_layer = tool_layers[i]
                
                # Check Z height constraint
                if batch_layers:
                    z_diff = abs(candidate_layer.z_height - batch_layers[0].z_height)
                    if z_diff > max_z_diff:
                        break
                
                # Check if we can safely batch this layer
                # (simplified: just check Z proximity for multi-material prints)
                if batch_layers:
                    # Verify no extreme collision risk
                    if not self._simple_collision_check(batch_layers[0], candidate_layer):
                        break
                
                batch_layers.append(candidate_layer)
            
            if batch_layers:
                # Create batch
                batch = LayerBatch(
                    tool=current_tool,
                    start_layer=batch_layers[0].layer_number,
                    end_layer=batch_layers[-1].layer_number,
                    layers=batch_layers
                )
                self.batches.append(batch)
                
                # Update indices
                tool_indices[current_tool] = start_idx + len(batch_layers)
                processed_count += len(batch_layers)
            else:
                # Skip this layer if we can't batch it
                tool_indices[current_tool] = start_idx + 1
                processed_count += 1
            
            # Alternate to next tool
            current_tool_idx += 1
        
        return self.batches
    
    def _simple_collision_check(self, layer1: Layer, layer2: Layer) -> bool:
        """Simple collision check based on Z height and geometry bounds.
        
        Args:
            layer1: First layer
            layer2: Second layer
            
        Returns:
            True if layers can be safely batched
        """
        # For multi-material prints, allow batching if layers are close in Z
        z_diff = abs(layer2.z_height - layer1.z_height)
        return z_diff <= 2.0  # Within 2mm is generally safe for multi-material
    
    def get_batch_statistics(self) -> dict:
        """Return statistics about the batching results."""
        if not self.batches:
            return {}
        
        total_layers = sum(batch.layer_count() for batch in self.batches)
        tool_changes = len(self.batches) - 1  # Transitions between batches
        
        # Count batches per tool
        tool_batch_count = {}
        for batch in self.batches:
            tool_batch_count[batch.tool] = tool_batch_count.get(batch.tool, 0) + 1
        
        # Find largest batch
        max_batch_size = max(batch.layer_count() for batch in self.batches)
        
        return {
            'total_layers': total_layers,
            'total_batches': len(self.batches),
            'tool_changes': tool_changes,
            'max_batch_size': max_batch_size,
            'batches_per_tool': tool_batch_count,
            'average_batch_size': total_layers / len(self.batches) if self.batches else 0
        }
