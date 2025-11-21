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
        
        Args:
            layers: List of all layers in the print
            
        Returns:
            List of layer batches
        """
        self.batches.clear()
        
        if not layers:
            return self.batches
        
        # Build geometry map for collision detection
        self.collision_detector.build_geometry_map(layers)
        
        i = 0
        while i < len(layers):
            current_layer = layers[i]
            current_tool = current_layer.tool
            
            # Find maximum batch size starting from this layer
            batch_size = self.collision_detector.find_maximum_batch_size(
                current_layer, layers, self.max_batch_layers
            )
            
            # Create batch
            batch_layers = layers[i:i + batch_size]
            batch = LayerBatch(
                tool=current_tool,
                start_layer=current_layer.layer_number,
                end_layer=layers[i + batch_size - 1].layer_number,
                layers=batch_layers
            )
            self.batches.append(batch)
            
            i += batch_size
        
        return self.batches
    
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
