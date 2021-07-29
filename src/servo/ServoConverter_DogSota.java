package servo;

import java.util.HashMap;
import java.util.Map;

import org.json.JSONObject;

public class ServoConverter_DogSota {

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
			case "BODY_Y": // -120 ~ 120 (servo: -150 ~ 150)
			    if      (val <-120) ret.put(id, (short) (-120 * 10));
			    else if (val > 120) ret.put(id, (short) ( 120 * 10));
			    else                ret.put(id, (short) (val  * 10));
			    continue;
			case "L_ELBO": // -90 ~ 65
			    if      (val < -90) ret.put(id, (short) (-90 * 10));
			    else if (val >  65) ret.put(id, (short) ( 65 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "R_ELBO": // -65 ~ 90
			    if      (val < -65) ret.put(id, (short) (-65 * 10));
			    else if (val >  90) ret.put(id, (short) ( 90 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "HEAD_P": // -27 ~ 5
			    if      (val < -27) ret.put(id, (short) (-27 * 10));
			    else if (val >   5) ret.put(id, (short) (  5 * 10));
			    else                ret.put(id, (short) (val * 10));
			    continue;
			case "HEAD_R": // -45 ~ 45
			    if      (val < -45) ret.put(id, (short) (-45 * 10));
			    else if (val >  45) ret.put(id, (short) ( 45 * 10));
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
