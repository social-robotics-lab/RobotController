package utils;

import org.json.JSONArray;
import org.json.JSONObject;

public class MotionExecutorThread implements Runnable {

	private JSONArray array;
	public MotionExecutorThread(JSONArray array) {
		this.array = array;
	}

	@Override
	public void run() {
		try {
			for (int i = 0; i < array.length(); i++) {
				JSONObject obj = array.getJSONObject(i);
				int msec = obj.getInt("Msec");
				PosePlayer.play(obj);
				Thread.sleep(msec);
			}
		} catch (InterruptedException e) {}
	}
}
