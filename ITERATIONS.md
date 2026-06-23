# ANDP Iteration Roadmap

This document tracks the evolution of the Apple Native Delivery Platform.

## Iteration 1: Foundation & MVP (Completed)
**Goal:** Build and publish a sample app to App Store Connect.
- [x] Repository structure and architecture diagrams.
- [x] `project.yml` contract and XcodeGen integration.
- [x] Base build scripts (`generate.sh`, `build.sh`, `archive.sh`).
- [x] Refined signing and export logic (`sign.sh`).
- [x] App Store Connect integration (`asc-manager.sh`).
- [x] CI/CD pipeline (GitHub Actions).
- [x] Sample App with extensions and assets.
- [x] Comprehensive `.gitignore`.

## Iteration 2: Testing & Quality Platform (Next)
**Goal:** Implement automated testing and basic validation.
- [ ] Unit and UI test orchestration (`test.sh`).
- [ ] Simulator management (`simulator-manager.sh`).
- [ ] Visual regression testing integration.
- [ ] Test report generation (`test-report.sh`).

## Iteration 3: Governance & Security
**Goal:** Advanced validation and compliance.
- [ ] Accessibility governance scripts.
- [ ] Localization validation.
- [ ] Security auditing and secret scanning.
- [ ] Certificate/Profile management.

## Iteration 4: Observability & AI
**Goal:** Insights and automated analysis.
- [ ] Build and test analytics collection.
- [ ] Performance monitoring (CPU, Memory, Startup).
- [ ] AI-powered architectural smell detection.
- [ ] Developer productivity dashboards.

## Iteration 5: Enterprise Maturity
**Goal:** Scale and documentation.
- [ ] Multi-team/Multi-account support.
- [ ] Distributed build preparation.
- [ ] Complete documentation suite (Migration, Security, Ops).
