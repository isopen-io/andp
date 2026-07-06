# Developer Guide

Welcome to the ANDP development team. This guide explains how to extend and maintain the platform.

## 1. Project Structure
- `Apps/`: Main application targets.
- `Features/`: Feature-specific modules (libraries).
- `Packages/`: Internal Swift Packages.
- `Infrastructure/`: Core logic (Bash/Python/Swift).
- `Documentation/`: Guides and diagrams.

## 2. Adding a New Target
1. Create the source directory in `Apps/` or `Features/`.
2. Add the target definition to `project.yml`.
3. Run `./generate.sh` to update the Xcode project.
4. Add the target to `build-matrix.sh` if it should be built automatically.

## 3. Extending the Build Pipeline
New orchestration scripts should follow these rules:
- Place core logic in `infrastructure/`.
- For App Store Connect related logic, place Python modules in `infrastructure/asc/`.
- Provide a root-level wrapper script.
- Support a `--help` flag.
- Log metrics using `infrastructure/analytics-manager.sh`.
- Avoid non-Apple dependencies.

## 4. Coding Standards
- **Bash:** Use `set -e`, use `[[ ]]` for tests, and quote variables.
- **Python:** Use Type Hints, follow PEP 8, and use `argparse` for CLI.
- **Swift:** Use modern concurrency (`async/await`) and follow the Swift Style Guide.

## 5. Testing Your Changes
Always run the infrastructure tests before submitting a PR:
```bash
./infrastructure/tests/run_tests.sh
```
If you modified build or test logic, run the matrices:
```bash
./build-matrix.sh
./test-matrix.sh
```
