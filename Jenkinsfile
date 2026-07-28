pipeline {
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
                sh './infrastructure/validate-project.sh'
                sh './infrastructure/tests/run_tests.sh'
                sh './test.sh'
                sh './infrastructure/governance-report.sh --full'
                sh './infrastructure/generate-dashboard.sh'
            }
        }
        stage('Archive & Sign') {
            steps {
                sh './archive.sh'
                sh './sign.sh .andp/build/*.xcarchive'
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: '.andp/build/exported/*.ipa, TestResults.xcresult/**, .andp/governance_report.md, .andp/dashboard.html', allowEmptyArchive: true
        }
    }
}
