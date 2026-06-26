# ANDP Architecture

## System Context Diagram
```mermaid
graph TD
    User[Developer / Release Engineer]
    ANDP[Apple Native Delivery Platform]
    ASC[App Store Connect]
    Git[Git Provider - GitHub/GitLab]
    AppleDev[Apple Developer Portal]

    User -->|Commands| ANDP
    ANDP -->|Generates/Builds| Apps[iOS/macOS/visionOS Apps]
    ANDP -->|Uploads| ASC
    ANDP -->|Pulls Code| Git
    ANDP -->|Manages Certs| AppleDev
```

## Container Diagram
```mermaid
graph TD
    subgraph ANDP
        Core[Core Orchestrator - Bash/Python]
        Gen[Project Generator - XcodeGen]
        Build[Build Engine - xcodebuild]
        Test[Test Platform - XCTest/Swift Testing]
        Sign[Signing Engine - codesign/security]
        Dist[Distribution Manager - ASC API]
    end

    Config[project.yml] --> Gen
    Gen --> Build
    Build --> Test
    Build --> Sign
    Sign --> Dist
    Dist --> ASC[App Store Connect]
```

## Component Diagram - Build & Release
```mermaid
graph LR
    subgraph Infrastructure
        build_sh[build.sh]
        archive_sh[archive.sh]
        sign_sh[sign.sh]
        asc_mgr[asc-manager.sh]
    end

    subgraph Logic
        PythonAPI[ASC Python Client]
        BashHelpers[Common Utilities]
    end

    archive_sh --> build_sh
    archive_sh --> sign_sh
    asc_mgr --> PythonAPI
    archive_sh --> asc_mgr
```

## Deployment Diagram
```mermaid
graph TD
    subgraph CI_Runner[macOS Runner]
        ANDP_Scripts[ANDP Scripts]
        Xcode[Xcode Toolchain]
        Simulator[iOS/tvOS/watchOS Simulators]
    end

    ANDP_Scripts --> Xcode
    Xcode --> Simulator
    ANDP_Scripts --> ASC_Cloud[App Store Connect Cloud]
```

## Sequence Diagram - Full Release Pipeline
```mermaid
sequenceDiagram
    participant Dev as Developer
    participant CI as CI/CD Pipeline
    participant ANDP as ANDP Scripts
    participant Xcode as xcodebuild
    participant ASC as App Store Connect

    Dev->>CI: Push to main
    CI->>ANDP: ./build-matrix.sh
    ANDP->>Xcode: build
    Xcode-->>ANDP: success
    CI->>ANDP: ./test-matrix.sh
    ANDP->>Xcode: test
    Xcode-->>ANDP: success
    CI->>ANDP: ./archive.sh
    ANDP->>Xcode: archive
    Xcode-->>ANDP: .xcarchive
    CI->>ANDP: ./sign.sh
    ANDP->>Xcode: exportArchive
    Xcode-->>ANDP: .ipa
    CI->>ANDP: ./asc-manager.sh upload
    ANDP->>ASC: POST /v1/builds
    ASC-->>ANDP: 201 Created
```

## Security Architecture Diagram
```mermaid
graph TD
    subgraph Secret_Storage
        SecretsFile[secrets.yml]
        EnvVars[Environment Variables]
    end

    subgraph Validation
        SecAudit[security-auditor.sh]
        SignVerify[codesign --verify]
    end

    subgraph Identity_Management
        CertMgr[certificate-manager.sh]
        Keychain[macOS Keychain]
    end

    SecretsFile --> SecAudit
    EnvVars --> SecAudit
    Keychain --> CertMgr
    CertMgr --> SignVerify
    SignVerify --> Artifacts[.ipa / .pkg]
```

## Data Flow Diagram
```mermaid
graph LR
    Code[Source Code] -->|Input| Build[Build System]
    Config[project.yml] -->|Input| Build
    Secrets[secrets.yml] -->|Credentials| Build
    Build -->|Artifacts| Sign[Signing System]
    Sign -->|Signed IPA| Dist[Distribution System]
    Build -->|Metrics| Analytics[Analytics System]
    Analytics -->|Report| Dash[HTML Dashboard]
```
