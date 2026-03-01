"""
Application Configuration
환경별 설정을 관리합니다.
"""

import os


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
