#!/usr/bin/env python3
"""
G-code Layer Batching Tool V2 for OrcaSlicer/Bambu Lab P1P
Batches objects across layers to reduce tool changes.

Strategy: Instead of alternating T0/T1 every layer, print all T0 objects 
for layers 1-N, then switch to T1 and print all T1 objects for layers 1-N.
"""

import re
from typing import List, Dict, Tuple


class LayerObject:
    """Represents a single object within a layer"""
    def __init__(self, layer_num: int, object_id: str, tool: str):
        self.layer_num = layer_num
        self.object_id = object_id
        self.tool = tool
        self.lines: List[str] = []
    
    def add_line(self, line: str):
        self.lines.append(line)


def parse_gcode_by_objects(input_file: str) -> Tuple[List[str], Dict[int, Dict[str, LayerObject]]]:
    """
    Parse G-code and organize by layer and object.
    
    Returns:
        preamble: Lines before first layer
        layers_dict: {layer_num: {object_id: LayerObject}}
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find first layer
    preamble_end = 0
    for i, line in enumerate(lines):
        if '; layer num/total_layer_count: 1/' in line:
            preamble_end = i
            break
    
    print(f"  Preamble ends at line {preamble_end}")
    preamble = lines[:preamble_end]
    
    # Parse objects within layers
    layers_dict = {}
    current_layer_num = None
    current_object = None
    current_tool = 'T0'
    layer_header_lines = []
    in_tool_change = False
    tool_change_lines = []
    
    for i, line in enumerate(lines[preamble_end:], start=preamble_end):
        # Detect layer start
        layer_match = re.search(r'; layer num/total_layer_count: (\d+)/(\d+)', line)
        if layer_match:
            current_layer_num = int(layer_match.group(1))
            if current_layer_num not in layers_dict:
                layers_dict[current_layer_num] = {}
            layer_header_lines = [line]
            continue
        
        # Detect object start
        object_start_match = re.search(r'; start printing object, unique label id: (\d+)', line)
        if object_start_match:
            object_id = object_start_match.group(1)
            if current_object:
                # Save previous object
                pass
            current_object = LayerObject(current_layer_num, object_id, current_tool)
            layers_dict[current_layer_num][object_id] = current_object
            # Add accumulated layer header
            for header_line in layer_header_lines:
                current_object.add_line(header_line)
            layer_header_lines = []
            current_object.add_line(line)
            continue
        
        # Detect object end
        object_end_match = re.search(r'; stop printing object, unique label id: (\d+)', line)
        if object_end_match:
            if current_object:
                current_object.add_line(line)
            current_object = None
            continue
        
        # Detect tool change
        tool_match = re.match(r'^T([01])$', line.strip())
        if tool_match:
            current_tool = line.strip()
            in_tool_change = True
            tool_change_lines = []
        
        # Collect tool change lines
        if in_tool_change:
            tool_change_lines.append(line)
            if 'M621 S' in line and 'A' in line:
                in_tool_change = False
            continue
        
        # Add line to current object or layer header
        if current_object:
            current_object.add_line(line)
        elif current_layer_num:
            layer_header_lines.append(line)
    
    return preamble, layers_dict


def reorganize_by_tool_batches(layers_dict: Dict[int, Dict[str, LayerObject]], 
                                batch_size: int = 10) -> List[str]:
    """
    Reorganize objects to batch by tool across layers.
    
    Strategy:
    - Print all T0 objects for layers 1-batch_size
    - Switch to T1, print all T1 objects for layers 1-batch_size  
    - Switch to T0, print all T0 objects for layers batch_size+1 to 2*batch_size
    - etc.
    """
    output_lines = []
    max_layer = max(layers_dict.keys())
    
    print(f"\nReorganizing {max_layer} layers with batch size {batch_size}...")
    
    # Determine tool change pattern
    current_tool = 'T0'
    num_batches = (max_layer + batch_size - 1) // batch_size
    
    for batch_idx in range(num_batches):
        start_layer = batch_idx * batch_size + 1
        end_layer = min((batch_idx + 1) * batch_size, max_layer)
        
        # Alternate tools for each batch
        tools = ['T0', 'T1'] if batch_idx % 2 == 0 else ['T1', 'T0']
        
        for tool in tools:
            print(f"  Batch {batch_idx+1}, {tool}: layers {start_layer}-{end_layer}")
            
            # Add tool change if needed
            if current_tool != tool:
                output_lines.extend(generate_tool_change(current_tool, tool))
                current_tool = tool
            
            # Print all objects of this tool for these layers
            for layer_num in range(start_layer, end_layer + 1):
                if layer_num in layers_dict:
                    for object_id, obj in layers_dict[layer_num].items():
                        if obj.tool == tool:
                            output_lines.extend(obj.lines)
    
    return output_lines


def generate_tool_change(from_tool: str, to_tool: str) -> List[str]:
    """Generate a simple tool change sequence"""
    # This is a simplified version - in reality we'd need the full purge/wipe sequence
    return [
        f"; Tool change: {from_tool} -> {to_tool}\n",
        f"{to_tool}\n",
        "G1 E2 F300 ; Prime after tool change\n",
    ]


def write_output(output_file: str, preamble: List[str], body_lines: List[str]):
    """Write the reorganized G-code"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(preamble)
        f.writelines(body_lines)
    print(f"\nOutput written to: {output_file}")


def main():
    input_file = 'input.gcode'
    output_file = 'output_v2.gcode'
    batch_size = 10
    
    print("="*60)
    print("G-code Layer Batching Tool V2")
    print("="*60)
    print(f"\nInput: {input_file}")
    print(f"Output: {output_file}")
    print(f"Batch size: {batch_size} layers\n")
    
    # Parse
    print("[1/3] Parsing G-code by objects...")
    preamble, layers_dict = parse_gcode_by_objects(input_file)
    
    total_objects = sum(len(objects) for objects in layers_dict.values())
    print(f"  Found {len(layers_dict)} layers")
    print(f"  Found {total_objects} total objects")
    
    # Reorganize
    print("\n[2/3] Reorganizing by tool batches...")
    body_lines = reorganize_by_tool_batches(layers_dict, batch_size)
    
    # Write
    print("\n[3/3] Writing output...")
    write_output(output_file, preamble, body_lines)
    
    print("\n" + "="*60)
    print("Done!")
    print("="*60)


if __name__ == '__main__':
    main()
