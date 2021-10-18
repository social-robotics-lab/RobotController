package utils;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.json.JSONObject;

public class IdleMotionPlayer {

	private static final Object lock = new Object();
	private static final ExecutorService service = Executors.newSingleThreadExecutor();
	private static Future<?> future;

	public static void play(double speed, int pause) {
		synchronized (lock) {
			future = service.submit(new IdleMotionExecutorThread(speed, pause));
		}
	}

	public static void play(JSONObject obj) {
		synchronized (lock) {
			double speed = (obj.has("Speed")) ? obj.getDouble("Speed") : 1.0;
			int pause = (obj.has("Pause")) ? obj.getInt("Pause") : 1000;
			play(speed, pause);
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
		future.cancel(true);
	}
}
