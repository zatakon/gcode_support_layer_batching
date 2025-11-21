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
            max_batch_layers: Maximum number of ACTUAL layers (not parser layers) to batch
        """
        self.collision_detector = collision_detector
        self.max_batch_layers = max_batch_layers
        self.batches: List[LayerBatch] = []
    
    def create_batches(self, layers: List[Layer]) -> List[LayerBatch]:
        """Create optimal layer batches from the input layers.
        
        For multi-object prints where the parser creates alternating "layers":
        - indices 0,2,4,6... = Object 1 (Tool 1)
        - indices 1,3,5,7... = Object 2 (Tool 0)
        
        We want to batch real layers together, e.g.:
        - Batch 1: Object 1, actual layers 1-5 (indices 0,2,4,6,8)
        - Batch 2: Object 2, actual layers 1-5 (indices 1,3,5,7,9)
        - Batch 3: Object 1, actual layers 6-10 (indices 10,12,14,16,18)
        - Batch 4: Object 2, actual layers 6-10 (indices 11,13,15,17,19)
        
        Args:
            layers: List of all parser-generated layers
            
        Returns:
            List of layer batches (REORDERED for batching efficiency)
        """
        self.batches.clear()
        
        if not layers:
            return self.batches
        
        # Build geometry map for collision detection
        self.collision_detector.build_geometry_map(layers)
        
        # Detect pattern: check if layers alternate tools consistently
        tools = [l.tool if l.tool is not None else 0 for l in layers]
        is_alternating = all(tools[i] != tools[i+1] for i in range(min(10, len(tools)-1)))
        
        if is_alternating and len(set(tools)) == 2:
            # Multi-object alternating pattern detected
            return self._create_interleaved_object_batches(layers, tools)
        else:
            # Simple sequential batching
            return self._create_sequential_batches(layers)
    
    def _create_interleaved_object_batches(self, layers: List[Layer], tools: List[int]) -> List[LayerBatch]:
        """Create batches for interleaved multi-object prints.
        
        Args:
            layers: All parser layers
            tools: Tool for each layer
            
        Returns:
            Reorganized batches
        """
        # Separate into two streams (even and odd indices)
        tool_0_layers = [layers[i] for i in range(len(layers)) if tools[i] == min(tools)]
        tool_1_layers = [layers[i] for i in range(len(layers)) if tools[i] == max(tools)]
        
        # Get the tool numbers
        tool_0 = min(tools)
        tool_1 = max(tools)
        
        # Create alternating batches
        idx_0 = 0
        idx_1 = 0
        
        while idx_0 < len(tool_0_layers) or idx_1 < len(tool_1_layers):
            # Batch for tool_0
            if idx_0 < len(tool_0_layers):
                end_idx = min(idx_0 + self.max_batch_layers, len(tool_0_layers))
                batch_layers = tool_0_layers[idx_0:end_idx]
                
                if batch_layers:
                    batch = LayerBatch(
                        tool=tool_0,
                        start_layer=batch_layers[0].layer_number,
                        end_layer=batch_layers[-1].layer_number,
                        layers=batch_layers
                    )
                    self.batches.append(batch)
                    idx_0 = end_idx
            
            # Batch for tool_1
            if idx_1 < len(tool_1_layers):
                end_idx = min(idx_1 + self.max_batch_layers, len(tool_1_layers))
                batch_layers = tool_1_layers[idx_1:end_idx]
                
                if batch_layers:
                    batch = LayerBatch(
                        tool=tool_1,
                        start_layer=batch_layers[0].layer_number,
                        end_layer=batch_layers[-1].layer_number,
                        layers=batch_layers
                    )
                    self.batches.append(batch)
                    idx_1 = end_idx
        
        return self.batches
    
    def _create_sequential_batches(self, layers: List[Layer]) -> List[LayerBatch]:
        """Create batches for sequential same-tool layers."""
        current_batch_layers = []
        current_tool = None
        
        for layer in layers:
            layer_tool = layer.tool if layer.tool is not None else 0
            
            should_start_new_batch = False
            
            if current_tool is None:
                current_tool = layer_tool
            elif current_tool != layer_tool:
                should_start_new_batch = True
            elif len(current_batch_layers) >= self.max_batch_layers:
                should_start_new_batch = True
            
            if should_start_new_batch and current_batch_layers:
                batch = LayerBatch(
                    tool=current_tool,
                    start_layer=current_batch_layers[0].layer_number,
                    end_layer=current_batch_layers[-1].layer_number,
                    layers=current_batch_layers
                )
                self.batches.append(batch)
                current_batch_layers = []
                current_tool = layer_tool
            
            current_batch_layers.append(layer)
        
        if current_batch_layers:
            batch = LayerBatch(
                tool=current_tool,
                start_layer=current_batch_layers[0].layer_number,
                end_layer=current_batch_layers[-1].layer_number,
                layers=current_batch_layers
            )
            self.batches.append(batch)
        
        return self.batches
    
    def get_batch_statistics(self) -> dict:
        """Return statistics about the batching results."""
        if not self.batches:
            return {}
        
        total_layers = sum(batch.layer_count() for batch in self.batches)
        tool_changes = len(self.batches) - 1
        
        tool_batch_count = {}
        for batch in self.batches:
            tool_batch_count[batch.tool] = tool_batch_count.get(batch.tool, 0) + 1
        
        max_batch_size = max(batch.layer_count() for batch in self.batches)
        
        return {
            'total_layers': total_layers,
            'total_batches': len(self.batches),
            'tool_changes': tool_changes,
            'max_batch_size': max_batch_size,
            'batches_per_tool': tool_batch_count,
            'average_batch_size': total_layers / len(self.batches) if self.batches else 0
        }
