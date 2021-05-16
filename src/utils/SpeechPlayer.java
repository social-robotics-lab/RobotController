package utils;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class SpeechPlayer {

	private static final Object lock = new Object();
	private static Process process;

	public static void play(Path path) {
		synchronized (lock) {
			try {
				process = new ProcessBuilder("aplay", path.toString()).start();
				process.waitFor();
			} catch (IOException e) {
				e.printStackTrace();
			} catch (InterruptedException e) {
				stop();
			}
		}
	}

	public static void play(byte[] bytes) {
		synchronized (lock) {
			try {
				Path path = Paths.get("__temp_wav");
				Files.write(path, bytes);
				process = new ProcessBuilder("aplay", path.toString()).start();
				process.waitFor();
			} catch (IOException e) {
				e.printStackTrace();
			} catch (InterruptedException e) {
				stop();
			}
		}
	}

	private static void stop() {
		if (process != null && process.isAlive()) {
			try {
				new ProcessBuilder("killall", "aplay").start();
				while (process.isAlive()) { Thread.sleep(10); }
			} catch (IOException | InterruptedException e) {
				e.printStackTrace();
			}
			process = null;
		}
	}

}
