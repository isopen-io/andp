#!/usr/bin/env python3

import os
import sys
import yaml

def load_project_config(filepath="project.yml"):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return None
    try:
        with open(filepath, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def build_dependency_graph(config):
    graph = {}
    targets = config.get("targets", {})

    for target_name, target_info in targets.items():
        dependencies = []
        deps = target_info.get("dependencies", [])
        for dep in deps:
            if "target" in dep:
                dependencies.append(dep["target"])
            elif "package" in dep:
                dependencies.append(f"pkg:{dep['package']}")
        graph[target_name] = dependencies

    return graph

def find_circular_dependencies(graph):
    def visit(node, visited, stack, path):
        visited.add(node)
        stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                cycle = visit(neighbor, visited, stack, path)
                if cycle:
                    return cycle
            elif neighbor in stack:
                return path + [neighbor]

        stack.remove(node)
        path.pop()
        return None

    visited = set()
    for node in graph:
        if node not in visited:
            cycle = visit(node, visited, set(), [])
            if cycle:
                return cycle
    return None

def generate_mermaid_graph(graph):
    lines = ["graph TD"]
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            lines.append(f"    {node} --> {neighbor}")
    return "\n".join(lines)

def main():
    print("ANDP Dependency Analyzer")
    print("=" * 30)

    config = load_project_config()
    if not config:
        sys.exit(1)

    graph = build_dependency_graph(config)

    # Check for circular dependencies
    cycle = find_circular_dependencies(graph)
    if cycle:
        print("❌ Circular dependency detected!")
        print(" -> ".join(cycle))
        sys.exit(1)
    else:
        print("✅ No circular dependencies detected.")

    # Generate report
    mermaid = generate_mermaid_graph(graph)
    os.makedirs("metrics", exist_ok=True)
    with open("metrics/dependency_graph.mermaid", "w") as f:
        f.write(mermaid)

    print(f"\nDependency graph generated: metrics/dependency_graph.mermaid")
    print("-" * 30)
    for target, deps in graph.items():
        print(f"{target}: {', '.join(deps) if deps else 'None'}")
    print("=" * 30)

if __name__ == "__main__":
    main()
