package main;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class Params {

	public static final String robotType;
	public static final int port;

	static {
		Properties properties = loadProperties("System.properties");
		// Robot type
		robotType = properties.getProperty("ROBOT_TYPE");
		checkNullProperties(robotType);
		// Server port
		final String strSpeechPort = properties.getProperty("PORT");
		checkNullProperties(strSpeechPort);
		checkIntProperties(strSpeechPort);
		port = Integer.valueOf(strSpeechPort);
	}

	private static Properties loadProperties(String path) {
		Properties properties = new Properties();
		File file = new File(path);
		try (InputStream input = new FileInputStream(file)) {
			properties.load(input);
		} catch (IOException e) {
			e.printStackTrace();
			System.exit(0);
		}
		return properties;
	}

	private static void checkNullProperties(String s) {
		if (s == null) {
			System.err.println("System.properties has no ["+ s +"].");
			System.exit(0);
		}
	}

	private static void checkIntProperties(String s) {
		try {
			Integer.parseInt(s);
		} catch (NumberFormatException e) {
			e.printStackTrace();
			System.exit(0);
		}
	}

}
