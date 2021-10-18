package utils;

import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.json.JSONObject;

import jp.vstone.RobotLib.CRobotPose;
import led.LedConverter;
import servo.RobotSys;
import servo.ServoConverter;

public class PoseExecutorThread implements Runnable {

	public static final BlockingQueue<JSONObject> q = new LinkedBlockingQueue<JSONObject>();

	@Override
	public void run() {
		RobotSys.initialize();
		try {
			while (true) {
				JSONObject obj = q.take();
				int msec = obj.getInt("Msec");
				CRobotPose pose = new CRobotPose();
				if (obj.has("ServoMap")) {
					Map<Byte, Short> servoMap = ServoConverter.jsonToMap(obj.getJSONObject("ServoMap"));
					pose.SetPose(servoMap);
				}
				if (obj.has("LedMap")) {
					Map<Byte, Short> ledMap = LedConverter.jsonToMap(obj.getJSONObject("LedMap"));
					pose.SetLed(ledMap);
				}
				play(msec, pose);
			}
		} catch (InterruptedException e) {
			e.printStackTrace();
		}
	}

	private void play(int msec, CRobotPose pose) {
		RobotSys.motion.play(pose, msec);
	}

}
