import cv2
import mediapipe as mp
import math
import sys
import json
import os

# Suppress TensorFlow and MediaPipe logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def calculate_angle(a, b, c):
    a = [a[0] - b[0], a[1] - b[1]]
    c = [c[0] - b[0], c[1] - b[1]]
    dot_product = a[0] * c[0] + a[1] * c[1]
    mag_a = math.hypot(a[0], a[1])
    mag_c = math.hypot(c[0], c[1])
    if mag_a * mag_c == 0:
        return 0
    angle = math.acos(dot_product / (mag_a * mag_c))
    return math.degrees(angle)


class PushUpDetector:
    def __init__(self):
        self.pose = mp.solutions.pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.counter = 0
        self.stage = "up"
        self.total_frames = 0
        self.valid_pose_frames = 0

    def detect(self, frame):
        self.total_frames += 1
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(image_rgb)

        if results.pose_landmarks:
            self.valid_pose_frames += 1
            lm = results.pose_landmarks.landmark

            # Left side keypoints
            l_shoulder = [lm[11].x, lm[11].y]
            l_elbow = [lm[13].x, lm[13].y]
            l_wrist = [lm[15].x, lm[15].y]
            l_hip = [lm[23].x, lm[23].y]
            l_ankle = [lm[27].x, lm[27].y]

            # Right side keypoints
            r_shoulder = [lm[12].x, lm[12].y]
            r_hip = [lm[24].x, lm[24].y]

            # Elbow angle
            elbow_angle = calculate_angle(l_shoulder, l_elbow, l_wrist)

            # Loosened side facing and body flat checks
            side_facing = abs(l_shoulder[0] - r_shoulder[0]) < 0.2 and abs(l_hip[0] - r_hip[0]) < 0.2
            body_flat = abs(l_shoulder[1] - l_hip[1]) < 0.25 and abs(l_hip[1] - l_ankle[1]) < 0.25

            if side_facing and body_flat:
                # Detect push-up down and up transitions
                if elbow_angle > 150 and self.stage == "down":
                    self.stage = "up"
                elif elbow_angle < 100 and self.stage == "up":
                    self.stage = "down"
                    self.counter += 1

        else:
            print("[Warning] No landmarks detected.", file=sys.stderr)


    def process_video(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(json.dumps({"error": f"Cannot open video file: {video_path}"}), file=sys.stdout)
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            self.detect(frame)

        cap.release()
        self.pose.close()

        accuracy = (
            self.valid_pose_frames / self.total_frames
            if self.total_frames > 0 else 0
        )

        print(json.dumps({
            "pushup_count": self.counter,
            "accuracy": round(accuracy*(70+3), 2)
        }))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Push-Up Detector - Video Only")
    parser.add_argument("--video", "-v", required=True, help="Path to video file")

    args = parser.parse_args()

    try:
        detector = PushUpDetector()
        detector.process_video(args.video)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
