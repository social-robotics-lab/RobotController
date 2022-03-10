package utils;

import java.util.HashMap;
import java.util.Map;

import main.Params;
import servo.RobotSys;

public class AxisReader {

	private static final Object lock = new Object();

	public static Map<Byte, Short> read() {
		synchronized (lock) {
			Map<Byte, Short> map = new HashMap<Byte, Short>();
			Byte[] ids = new Byte[0];

			if      (Params.robotType.equals("CommU")) {
				Byte[] temp = {(byte)1, (byte)2, (byte)3,  (byte)4,  (byte)5,  (byte)6,  (byte)7,
					           (byte)8, (byte)9, (byte)10, (byte)11, (byte)12, (byte)13, (byte)14};
				ids = temp.clone();
			}
			else if (Params.robotType.equals("Sota")) {
				Byte[] temp = {(byte)1, (byte)2, (byte)3, (byte)4,
							   (byte)5, (byte)6, (byte)7, (byte)8};
				ids = temp.clone();
			}
			else if (Params.robotType.equals("Dog")) {
				Byte[] temp = {(byte)1, (byte)3, (byte)5, (byte)7, (byte)8};
				ids = temp.clone();
			}
			else {
				System.err.println("Robot type is wrong. Current robot type is '" + Params.robotType + "'");
				System.exit(0);
			}

			Short[] vals = RobotSys.motion.getReadpos();
			if (vals == null){
				return map;
			}
			for (int i = 0; i < vals.length; i++) {
				map.put(ids[i], vals[i]);
			}
			return map;
		}
	}
}
