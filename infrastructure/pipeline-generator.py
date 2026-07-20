#!/usr/bin/env python3

import os
import sys

def generate_gitlab_ci():
    content = """stages:
  - bootstrap
  - generate
  - build
  - test
  - governance
  - archive
  - sign
  - deploy

variables:
  LC_ALL: "en_US.UTF-8"
  LANG: "en_US.UTF-8"

bootstrap:
  stage: bootstrap
  script:
    - ./infrastructure/bootstrap.sh
  tags:
    - macos

generate:
  stage: generate
  script:
    - ./generate.sh
  tags:
    - macos
  artifacts:
    paths:
      - "*.xcodeproj"
      - "*.xcworkspace"

build:
  stage: build
  script:
    - ./build.sh
  tags:
    - macos

test:
  stage: test
  script:
    - ./test.sh
  tags:
    - macos
  artifacts:
    when: always
    paths:
      - TestResults.xcresult
      - metrics/

governance:
  stage: governance
  script:
    - ./infrastructure/sbom-generator.sh
    - ./infrastructure/security-auditor.sh
    - ./infrastructure/governance-report.sh
    - ./infrastructure/generate-dashboard.sh
  tags:
    - macos
  artifacts:
    paths:
      - governance_report.md
      - dashboard.html
      - metrics/

archive:
  stage: archive
  script:
    - ./archive.sh
  tags:
    - macos
  artifacts:
    paths:
      - build/*.xcarchive

sign:
  stage: sign
  script:
    - ./sign.sh build/*.xcarchive
  tags:
    - macos
  artifacts:
    paths:
      - build/exported/*.ipa

deploy:
  stage: deploy
  script:
    - ./asc-manager.sh upload build/exported/*.ipa
  tags:
    - macos
  only:
    - main
    - tags
"""
    with open(".gitlab-ci.yml", "w") as f:
        f.write(content)
    print("✅ Generated .gitlab-ci.yml")

def generate_azure_pipelines():
    content = """trigger:
- main

pool:
  vmImage: 'macOS-latest'

stages:
- stage: Build
  jobs:
  - job: BuildAndTest
    steps:
    - script: ./infrastructure/bootstrap.sh
      displayName: 'Bootstrap'
    - script: ./generate.sh
      displayName: 'Generate Project'
    - script: ./build.sh
      displayName: 'Build'
    - script: ./test.sh
      displayName: 'Test'
    - script: ./infrastructure/governance-report.sh --full
      displayName: 'Governance Audit'
    - script: ./infrastructure/generate-dashboard.sh
      displayName: 'Generate Dashboard'
    - script: ./archive.sh
      displayName: 'Archive'
    - script: ./sign.sh build/*.xcarchive
      displayName: 'Sign'
    - task: PublishBuildArtifacts@1
      inputs:
        PathtoPublish: 'build/exported'
        ArtifactName: 'ipa'
    - task: PublishBuildArtifacts@1
      inputs:
        PathtoPublish: 'governance_report.md'
        ArtifactName: 'governance'
"""
    with open("azure-pipelines.yml", "w") as f:
        f.write(content)
    print("✅ Generated azure-pipelines.yml")

def generate_jenkinsfile():
    content = """pipeline {
    agent { label 'macos' }
    stages {
        stage('Bootstrap') {
            steps {
                sh './infrastructure/bootstrap.sh'
            }
        }
        stage('Generate') {
            steps {
                sh './generate.sh'
            }
        }
        stage('Build') {
            steps {
                sh './build.sh'
            }
        }
        stage('Test & Governance') {
            steps {
                sh './test.sh'
                sh './infrastructure/governance-report.sh --full'
                sh './infrastructure/generate-dashboard.sh'
            }
        }
        stage('Archive & Sign') {
            steps {
                sh './archive.sh'
                sh './sign.sh build/*.xcarchive'
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'build/exported/*.ipa, TestResults.xcresult/**, governance_report.md, dashboard.html', allowEmptyArchive: true
        }
    }
}
"""
    with open("Jenkinsfile", "w") as f:
        f.write(content)
    print("✅ Generated Jenkinsfile")

def main():
    print("ANDP Pipeline Generator (Iteration 9 Optimized)")
    print("=" * 30)
    generate_gitlab_ci()
    generate_azure_pipelines()
    generate_jenkinsfile()
    print("=" * 30)

if __name__ == "__main__":
    main()
