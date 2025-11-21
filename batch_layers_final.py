#!/usr/bin/env python3
"""
G-code Layer Batching Tool - Final Version
Reorganizes multi-material prints to batch objects by tool across layers.
"""

import re
from typing import List, Dict, Tuple


class PrintObject:
    """Represents one object in one layer"""
    def __init__(self, layer_num, object_id, tool):
        self.layer_num = layer_num
        self.object_id = object_id
        self.tool = tool
        self.lines = []


def parse_gcode_objects(input_file):
    """Parse G-code and extract objects by layer"""
    print("  Reading file...")
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"  Read {len(lines)} lines")
    
    # Find first layer
    preamble_end = 0
    for i, line in enumerate(lines):
        if '; layer num/total_layer_count: 1/' in line:
            preamble_end = i
            break
    
    print(f"  Preamble ends at line {preamble_end}")
    preamble = lines[:preamble_end]
    
    # Parse objects
    objects_by_layer = {}
    current_layer_num = None
    current_object = None
    current_tool = 'T0'
    in_object = False
    in_tool_change = False
    
    print(f"  Parsing objects...")
    for line in lines[preamble_end:]:
        # Detect layer
        layer_match = re.search(r'; layer num/total_layer_count: (\d+)/(\d+)', line)
        if layer_match:
            current_layer_num = int(layer_match.group(1))
            if current_layer_num not in objects_by_layer:
                objects_by_layer[current_layer_num] = []
            continue
        
        # Detect tool change
        tool_match = re.match(r'^T([01])$', line.strip())
        if tool_match:
            current_tool = line.strip()
            in_tool_change = True
        
        # Skip tool change sequences
        if in_tool_change:
            if 'M621 S' in line and 'A' in line:
                in_tool_change = False
            continue
        
        # Detect object start
        if '; start printing object, unique label id:' in line:
            match = re.search(r'unique label id: (\d+)', line)
            if match:
                object_id = match.group(1)
                current_object = PrintObject(current_layer_num, object_id, current_tool)
                objects_by_layer[current_layer_num].append(current_object)
                in_object = True
                current_object.lines.append(line)
                continue
        
        # Detect object end
        if '; stop printing object, unique label id:' in line:
            if current_object:
                current_object.lines.append(line)
            in_object = False
            current_object = None
            continue
        
        # Add line to current object
        if in_object and current_object:
            current_object.lines.append(line)
    
    return preamble, objects_by_layer


def generate_tool_change(from_tool, to_tool):
    """Generate simplified tool change sequence"""
    tool_num = '0' if to_tool == 'T0' else '1'
    return [
        f"\n; ===== Tool change: {from_tool} -> {to_tool} =====\n",
        f"M620 S{tool_num}A\n",
        "M204 S9000\n",
        "G17\n",
        "G2 Z0.6 I0.86 J0.86 P1 F10000\n",
        "G1 Z3.2 F1200\n",
        "G1 X70 F21000\n",
        "G1 Y245\n",
        "G1 Y265 F3000\n",
        "M400\n",
        "M106 P1 S0\n",
        "M106 P2 S0\n",
        "M104 S220\n",
        "M620.11 S0\n",
        "M400\n",
        "G1 X90\n",
        "G1 Y255 F4000\n",
        "G1 X100 F5000\n",
        "G1 X120 F15000\n",
        "G1 X20 Y50 F21000\n",
        "G1 Y-3\n",
        "M620.1 E F299 T240\n",
        f"{to_tool}\n",
        "M620.1 E F299 T240\n",
        "M620.11 S0\n",
        "G92 E0\n",
        "; FLUSH_START\n",
        "M400\n",
        "M109 S220\n",
        "G1 E2 F299\n",
        "; FLUSH_END\n",
        "M400\n",
        "G92 E0\n",
        "G1 E-2 F1800\n",
        "M106 P1 S255\n",
        "M400 S3\n",
        "G1 X70 F5000\n",
        "G1 X90 F3000\n",
        "G1 Y255 F4000\n",
        "G1 X105 F5000\n",
        "G1 Y265\n",
        "G1 X70 F10000\n",
        "G1 X100 F5000\n",
        "G1 X70 F10000\n",
        "G1 X100 F5000\n",
        "G1 X70 F10000\n",
        "G1 X80 F15000\n",
        "G1 X60\n",
        "G1 X80\n",
        "G1 X60\n",
        "G1 X80\n",
        "G1 X100 F5000\n",
        "G1 X165 F15000\n",
        "G1 Y256\n",
        "M400\n",
        "G1 Z3.2 F3000\n",
        "M204 S10000\n",
        f"M621 S{tool_num}A\n",
        "M106 S0\n",
        "M104 S220\n",
        "M900 K0.015 L1000 M10\n",
    ]


def reorganize_by_batches(objects_by_layer, batch_size=5):
    """Reorganize objects into tool batches"""
    output_lines = []
    max_layer = max(objects_by_layer.keys())
    num_batches = (max_layer + batch_size - 1) // batch_size
    
    print(f"\nReorganizing into {num_batches} batches...")
    
    current_tool = 'T0'
    
    for batch_idx in range(num_batches):
        start_layer = batch_idx * batch_size + 1
        end_layer = min((batch_idx + 1) * batch_size, max_layer)
        
        # Alternate tool order
        if batch_idx % 2 == 0:
            tool_order = ['T0', 'T1']
        else:
            tool_order = ['T1', 'T0']
        
        print(f"\nBatch {batch_idx + 1} (layers {start_layer}-{end_layer}):")
        
        for tool in tool_order:
            # Add tool change if needed
            if current_tool != tool:
                print(f"  Tool change: {current_tool} -> {tool}")
                output_lines.extend(generate_tool_change(current_tool, tool))
                current_tool = tool
            
            # Print all objects of this tool
            objects_printed = 0
            for layer_num in range(start_layer, end_layer + 1):
                if layer_num in objects_by_layer:
                    for obj in objects_by_layer[layer_num]:
                        if obj.tool == tool:
                            output_lines.extend(obj.lines)
                            objects_printed += 1
            
            print(f"  {tool}: {objects_printed} objects")
    
    return output_lines


def main():
    input_file = 'input.gcode'
    output_file = 'output.gcode'
    batch_size = 5
    
    print("="*70)
    print("G-code Layer Batching Tool")
    print("="*70)
    print(f"\nInput: {input_file}")
    print(f"Output: {output_file}")
    print(f"Batch size: {batch_size} layers\n")
    
    # Parse
    print("[1/3] Parsing G-code...")
    preamble, objects_by_layer = parse_gcode_objects(input_file)
    
    total_layers = len(objects_by_layer)
    total_objects = sum(len(objs) for objs in objects_by_layer.values())
    t0_count = sum(1 for objs in objects_by_layer.values() for obj in objs if obj.tool == 'T0')
    t1_count = sum(1 for objs in objects_by_layer.values() for obj in objs if obj.tool == 'T1')
    
    print(f"\n  Total layers: {total_layers}")
    print(f"  Total objects: {total_objects}")
    print(f"    T0: {t0_count}")
    print(f"    T1: {t1_count}")
    
    # Reorganize
    print("\n[2/3] Reorganizing...")
    body_lines = reorganize_by_batches(objects_by_layer, batch_size)
    
    # Write
    print("\n[3/3] Writing output...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(preamble)
        f.writelines(body_lines)
    
    print(f"\nOutput written to: {output_file}")
    
    # Stats
    original_changes = total_layers - 1
    num_batches = (total_layers + batch_size - 1) // batch_size
    new_changes = num_batches
    reduction = original_changes - new_changes
    
    print(f"\nTool changes:")
    print(f"  Original: {original_changes}")
    print(f"  New: {new_changes}")
    print(f"  Reduction: {reduction} ({100*reduction/original_changes:.1f}%)")
    
    print("\n" + "="*70)
    print("Done! TEST THE OUTPUT CAREFULLY!")
    print("="*70)


if __name__ == '__main__':
    main()
