package utils;

import java.util.Map;

import org.json.JSONObject;

import servo.ServoConverter;

public class PosePlayer {

	private static final Object lock = new Object();

	public static void play(JSONObject obj) {
		synchronized (lock) {
			if (!obj.has("Msec")) return;
			if (!obj.has("ServoMap") && !obj.has("LedMap")) return;
			try {
				PoseExecutorThread.q.put(obj);
			} catch (InterruptedException e) {}
		}
	}

	public static void play(String text) {
		synchronized (lock) {
			JSONObject obj = new JSONObject(text);
			play(obj);
		}
	}

	public static void play(byte[] bytes) {
		synchronized (lock) {
			String text = new String(bytes);
			play(text);
		}
	}

	public static void stop() {
		synchronized (lock) {
			Map<Byte, Short> servoMap = AxisReader.read();
			JSONObject servoMapObj = ServoConverter.mapToJson(servoMap);
			JSONObject obj = new JSONObject();
			obj.put("Msec", 100);
			obj.put("ServoMap", servoMapObj);
			play(obj);
		}
	}
}
