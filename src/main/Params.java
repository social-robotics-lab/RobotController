package main;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class Params {

	public static final String robotType;
	public static final int speechPort;
	public static final int posePort;
	public static final int readPort;

	static {
		Properties properties = loadProperties("System.properties");
		// Robot type
		robotType = properties.getProperty("ROBOT_TYPE");
		checkNullProperties(robotType);
		// Server port
		final String strSpeechPort = properties.getProperty("SPEECH_PORT");
		checkNullProperties(strSpeechPort);
		checkIntProperties(strSpeechPort);
		speechPort = Integer.valueOf(strSpeechPort);
		final String strPosePort = properties.getProperty("POSE_PORT");
		checkNullProperties(strPosePort);
		checkIntProperties(strPosePort);
		posePort = Integer.valueOf(strPosePort);
		final String strReadPort = properties.getProperty("READ_PORT");
		checkNullProperties(strReadPort);
		checkIntProperties(strReadPort);
		readPort = Integer.valueOf(strReadPort);
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
