package utils;

import jp.vstone.RobotLib.CRobotPose;
import main.RobotSys;

public class PosePlayer {

	private static final Object lock = new Object();

	public static void play(int msec, CRobotPose pose) {
		synchronized (lock) {
			RobotSys.motion.play(pose, msec);
		}
	}

}
