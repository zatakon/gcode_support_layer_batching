#!/usr/bin/env python3
"""
G-code Layer Batching Tool for OrcaSlicer/Bambu Lab P1P
Merges consecutive layers to reduce tool changes.
"""

import re
from typing import List, Tuple, Optional


class Layer:
    """Represents a single layer in the G-code"""
    def __init__(self, layer_num: int, tool: str):
        self.layer_num = layer_num
        self.tool = tool  # 'T0' or 'T1'
        self.lines: List[str] = []
        self.has_tool_change = False
        
    def add_line(self, line: str):
        self.lines.append(line)


def parse_gcode(input_file: str) -> Tuple[List[str], List[Layer]]:
    """
    Parse G-code file and extract preamble and layers
    
    Returns:
        preamble: Lines before first layer (includes startup sequence)
        layers: List of Layer objects
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the first layer marker - everything before is preamble
    preamble_end = 0
    for i, line in enumerate(lines):
        if '; layer num/total_layer_count: 1/' in line:
            preamble_end = i
            break
    
    print(f"  Preamble ends at line {preamble_end} (includes startup sequence)")
    preamble = lines[:preamble_end]
    
    # Parse layers
    layers = []
    current_layer = None
    current_tool = 'T0'  # Start with T0
    
    for i, line in enumerate(lines[preamble_end:], start=preamble_end):
        # Detect tool change
        tool_match = re.match(r'^T([01])$', line.strip())
        if tool_match:
            current_tool = line.strip()
            print(f"  Tool change detected at line {i}: {current_tool}")
        
        # Detect layer start
        layer_match = re.search(r'; layer num/total_layer_count: (\d+)/(\d+)', line)
        if layer_match:
            layer_num = int(layer_match.group(1))
            
            # Save previous layer
            if current_layer:
                layers.append(current_layer)
                print(f"  Saved layer {current_layer.layer_num} with tool {current_layer.tool}, {len(current_layer.lines)} lines")
            
            # Create new layer with the current tool
            current_layer = Layer(layer_num, current_tool)
            print(f"  Starting layer {layer_num} with tool {current_tool}")
        
        # Add line to current layer
        if current_layer:
            current_layer.add_line(line)
    
    # Don't forget the last layer
    if current_layer:
        layers.append(current_layer)
        print(f"  Saved final layer {current_layer.layer_num} with tool {current_layer.tool}, {len(current_layer.lines)} lines")
    
    return preamble, layers


def analyze_and_batch_layers(layers: List[Layer], max_batch_size: int = 10) -> List[Layer]:
    """
    Analyze layers and determine batching opportunities.
    Keep original tool assignments but batch consecutive layers with the same tool.
    
    Args:
        layers: List of parsed layers with original tool assignments
        max_batch_size: Maximum number of consecutive layers to batch together
    
    Returns:
        List of layers (tool assignments unchanged, ready for tool change removal)
    """
    if not layers:
        return layers
    
    print(f"Analyzing {len(layers)} layers for batching opportunities...")
    print(f"  Max batch size: {max_batch_size} layers")
    
    # Identify batches of consecutive same-tool layers
    batches = []
    current_batch_start = 0
    current_batch_tool = layers[0].tool
    
    for i in range(1, len(layers) + 1):
        # Check if we need to start a new batch
        if i == len(layers) or layers[i].tool != current_batch_tool:
            # Save current batch
            batch_size = i - current_batch_start
            batches.append({
                'tool': current_batch_tool,
                'start': current_batch_start,
                'end': i,
                'size': batch_size
            })
            
            if i < len(layers):
                # Start new batch
                current_batch_start = i
                current_batch_tool = layers[i].tool
    
    # Report batching opportunities
    print(f"\nFound {len(batches)} natural batches:")
    for idx, batch in enumerate(batches):
        layers_str = f"layers {batch['start']+1}-{batch['end']}"
        print(f"  Batch {idx+1}: {batch['tool']}, {batch['size']} layers ({layers_str})")
    
    return layers


def update_tool_changes(layers: List[Layer]) -> List[Layer]:
    """
    Update tool change sequences to match the batching plan.
    - When consecutive layers use the SAME tool: remove the tool change
    - When consecutive layers use DIFFERENT tools: ensure tool change exists and update the T command
    """
    for i in range(len(layers)):
        current_layer = layers[i]
        prev_layer = layers[i - 1] if i > 0 else None
        next_layer = layers[i + 1] if i < len(layers) - 1 else None
        
        # Check if this layer has a tool change section
        has_tool_change = any('M620 S' in line and 'A' in line for line in current_layer.lines)
        
        if next_layer and current_layer.tool == next_layer.tool:
            # SAME TOOL → Remove tool change section at end of current layer
            if has_tool_change:
                new_lines = []
                skip_section = False
                
                for line in current_layer.lines:
                    # Detect start of tool change section (M620 S0A or M620 S1A)
                    if re.match(r'^M620 S[01]A', line.strip()):
                        skip_section = True
                        continue
                    
                    # Detect tool change command
                    if re.match(r'^T[01]$', line.strip()):
                        continue
                    
                    # Detect end of tool change section
                    if skip_section and 'M621 S' in line:
                        skip_section = False
                        continue
                    
                    # Skip purge/flush sections
                    if 'FLUSH_START' in line:
                        skip_section = True
                    if 'FLUSH_END' in line:
                        skip_section = False
                        continue
                    
                    # Skip G-code between tool change start and end
                    if skip_section:
                        # Skip movement, extrusion, temp, and other commands during tool change
                        continue
                    
                    new_lines.append(line)
                
                current_layer.lines = new_lines
        
        elif next_layer and current_layer.tool != next_layer.tool:
            # DIFFERENT TOOL → Ensure tool change exists and update T command to next tool
            if has_tool_change:
                # Update existing tool change to use the correct next tool
                new_lines = []
                for line in current_layer.lines:
                    # Replace T0/T1 commands with the next layer's tool
                    if re.match(r'^T[01]$', line.strip()):
                        new_lines.append(f"{next_layer.tool}\n")
                    else:
                        new_lines.append(line)
                current_layer.lines = new_lines
    
    return layers


def write_gcode(output_file: str, preamble: List[str], layers: List[Layer]):
    """Write the batched G-code to output file"""
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write preamble
        f.writelines(preamble)
        
        # Write layers
        for layer in layers:
            f.writelines(layer.lines)
    
    print(f"\nOutput written to: {output_file}")


def main():
    input_file = 'input.gcode'
    output_file = 'output.gcode'
    
    print("="*60)
    print("G-code Layer Batching Tool")
    print("="*60)
    print(f"\nInput file: {input_file}")
    print(f"Output file: {output_file}")
    print("\nStrategy: Keep original tool/object assignments, batch consecutive same-tool layers")
    
    # Parse
    print("\n[1/4] Parsing G-code...")
    preamble, layers = parse_gcode(input_file)
    print(f"  Found {len(layers)} layers")
    print(f"  Preamble: {len(preamble)} lines")
    
    # Analyze original
    print("\n[2/4] Analyzing original tool changes...")
    tool_changes = 0
    for i in range(len(layers) - 1):
        if layers[i].tool != layers[i+1].tool:
            tool_changes += 1
    print(f"  Original tool changes: {tool_changes}")
      # Analyze batching opportunities
    print("\n[3/4] Analyzing batching opportunities...")
    max_batch_size = 10  # Maximum layers to batch together
    layers = analyze_and_batch_layers(layers, max_batch_size)
      # Update tool changes based on batching
    print("\n[4/4] Updating tool changes for batching...")
    layers = update_tool_changes(layers)
    
    # Analyze result
    new_tool_changes = 0
    for i in range(len(layers) - 1):
        if layers[i].tool != layers[i+1].tool:
            new_tool_changes += 1
    print(f"  New tool changes: {new_tool_changes}")
    print(f"  Reduction: {tool_changes - new_tool_changes} ({100*(tool_changes - new_tool_changes)/max(tool_changes, 1):.1f}%)")
    
    # Write output
    write_gcode(output_file, preamble, layers)
    
    print("\n" + "="*60)
    print("Done!")
    print("="*60)


if __name__ == '__main__':
    main()
