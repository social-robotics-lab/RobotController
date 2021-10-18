package utils;

import org.json.JSONObject;

import servo.RobotSys;

public class IdleMotionExecutorThread implements Runnable {

	private final double speed;
	private final int pause;
	private int index;

	public IdleMotionExecutorThread(double speed, int pause) {
		this.speed = speed;
		this.pause = pause;
		index = 0;
	}

	@Override
	public void run() {
		try {
			while (true) {
				JSONObject obj = new JSONObject();
				int msec = (int)(1000 / speed);
				obj.put("Msec", msec);
				obj.put("ServoMap", RobotSys.idleServoMaps.getJSONObject(index));
				index = (index == 0) ? index + 1 : 0;
				PosePlayer.play(obj);
				Thread.sleep(msec + pause);
			}
		} catch (InterruptedException e) {}
	}
}
