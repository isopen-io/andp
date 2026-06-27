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
        stage('Test') {
            steps {
                sh './test.sh'
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
            archiveArtifacts artifacts: 'build/exported/*.ipa, TestResults.xcresult/**', allowEmptyArchive: true
        }
    }
}
