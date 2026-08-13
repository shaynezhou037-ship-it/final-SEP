from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'dual_berxel_calibration'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(),
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name],
        ),
        (
            'share/' + package_name,
            ['package.xml'],
        ),
        (
            os.path.join('share', package_name, 'config'),
            glob('config/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py'),
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='yunkai_chou',
    maintainer_email='yunkai_chou@example.com',
    description='Dual Berxel checkerboard calibration and pose detection.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'accuracy_recorder = dual_berxel_calibration.accuracy_recorder:main',
            'dual_point_fusion = dual_berxel_calibration.dual_point_fusion:main',
            'aruco_depth_point_estimator = dual_berxel_calibration.aruco_depth_point_estimator:main',
            'checkerboard_pose_detector = dual_berxel_calibration.checkerboard_pose_detector:main',
            'dual_camera_extrinsic_calibrator = dual_berxel_calibration.dual_camera_extrinsic_calibrator:main',
        ],
    },
)
