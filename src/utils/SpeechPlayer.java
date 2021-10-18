package utils;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class SpeechPlayer {

	private static final Object lock = new Object();
	private static Process process;


	public static void play(Path path) throws IOException {
		synchronized (lock) {
			process = new ProcessBuilder("aplay", path.toString()).start();
		}
	}

	public static void play(byte[] bytes) throws IOException {
		synchronized (lock) {
			Path path = Paths.get("__temp_wav");
			Files.write(path, bytes);
			play(path);
		}
	}

	public static void stop() {
		synchronized (lock) {
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
}
