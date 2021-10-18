package utils;

import java.util.HashMap;
import java.util.Map;

import servo.RobotSys;

public class AxisReader {

	private static final Object lock = new Object();

	public static Map<Byte, Short> read() {
		synchronized (lock) {
			Map<Byte, Short> map = new HashMap<Byte, Short>();
			Short[] vals = RobotSys.motion.getReadpos();
			if (vals == null){
				return map;
			}
			for (int i = 0; i < vals.length; i++) {
				map.put((byte)(i + 1), vals[i]);
			}
			return map;
		}
	}
}
