package utils;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.json.JSONArray;

public class MotionPlayer {

	private static final Object lock = new Object();
	private static final ExecutorService service = Executors.newSingleThreadExecutor();
	private static Future<?> future;

	public static void play(JSONArray array) {
		synchronized (lock) {
			future = service.submit(new MotionExecutorThread(array));
		}
	}

	public static void play(String text) {
		synchronized (lock) {
			JSONArray array = new JSONArray(text);
			play(array);
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
