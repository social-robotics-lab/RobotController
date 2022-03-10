package servo;

import java.util.HashMap;
import java.util.Map;

import org.json.JSONObject;

public class ServoConverter_Dog {

	private static final Map<String, Byte> map = new HashMap<String, Byte>() {
		{
			put("BODY_Y", (byte) 1);
			put("L_ELBO", (byte) 3);
			put("R_ELBO", (byte) 5);
			put("HEAD_P", (byte) 7);
			put("HEAD_R", (byte) 8);
		}
	};

	public static Map<Byte, Short> jsonToMap(JSONObject json) {
		Map<Byte, Short> ret = new HashMap<Byte, Short>();
		for (String key : json.keySet()) {
			byte id = map.get(key);
			int val = json.getInt(key);
			switch (key) {
			case "BODY_Y": // -80 ~ 80
			    if      (val < -80) ret.put(id, (short) (-80 * 10));
			    else if (val >  80) ret.put(id, (short) ( 80 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "L_ELBO": // -70 ~ 70
			    if      (val < -70) ret.put(id, (short) (-70 * 10));
			    else if (val >  70) ret.put(id, (short) ( 70 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "R_ELBO": // -70 ~ 70
			    if      (val < -70) ret.put(id, (short) (-70 * 10));
			    else if (val >  70) ret.put(id, (short) ( 70 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "HEAD_P": // -70 ~ 70
			    if      (val < -70) ret.put(id, (short) (-70 * 10));
			    else if (val >  70) ret.put(id, (short) ( 70 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "HEAD_R": // -50 ~ 50
			    if      (val < -50) ret.put(id, (short) (-50 * 10));
			    else if (val >  50) ret.put(id, (short) ( 50 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			}
		}
		return ret;
	}

	public static JSONObject mapToJson(Map<Byte, Short> map) {
		JSONObject ret = new JSONObject();
		for (Byte id : map.keySet()) {
			int val = map.get(id).intValue();
			switch (id) {
			case 1:
				ret.put("BODY_Y", (int) (val / 10));
				continue;
			case 3:
				ret.put("L_ELBO", (int) (val / 10));
				continue;
			case 5:
				ret.put("R_ELBO", (int) (val / 10));
				continue;
			case 7:
				ret.put("HEAD_P", (int) (val / 10));
				continue;
			case 8:
				ret.put("HEAD_R", (int) (val / 10));
				continue;
			}
		}
		return ret;
	}
}
