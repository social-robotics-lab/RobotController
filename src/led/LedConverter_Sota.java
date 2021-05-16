package led;

import java.util.HashMap;
import java.util.Map;

import org.json.JSONObject;

public class LedConverter_Sota {

	private static final Map<String, Byte> map = new HashMap<String, Byte>() {
		{
			put("PWR_BTN_R", (byte)  0);
			put("PWR_BTN_G", (byte)  1);
			put("PWR_BTN_B", (byte)  2);
			put("R_EYE_R",   (byte)  8);
			put("R_EYE_G",   (byte)  9);
			put("R_EYE_B",   (byte) 10);
			put("L_EYE_R",   (byte) 11);
			put("L_EYE_G",   (byte) 12);
			put("L_EYE_B",   (byte) 13);
			put("MOUTH",     (byte) 14);
		}
	};

	public static Map<Byte, Short> jsonToMap(JSONObject json) {
		Map<Byte, Short> ret = new HashMap<Byte, Short>();
		for (String key : json.keySet()) {
			byte id = map.get(key);
			int val = json.getInt(key);
			if      (val < 0)   val = 0;
			else if (val > 255) val = 255;
			ret.put(id, (short) val);
		}
		return ret;
	}

	public static JSONObject mapToJson(Map<Byte, Short> map) {
		JSONObject ret = new JSONObject();
		for (Byte id : map.keySet()) {
			int val = map.get(id).intValue();
			switch (id) {
			case 0:
				ret.put("PWR_BTN_R", (int) val);
				continue;
			case 1:
				ret.put("PWR_BTN_G", (int) val);
				continue;
			case 2:
				ret.put("PWR_BTN_B", (int) val);
				continue;
			case 8:
				ret.put("R_EYE_R", (int) val);
				continue;
			case 9:
				ret.put("R_EYE_G", (int) val);
				continue;
			case 10:
				ret.put("R_EYE_B", (int) val);
				continue;
			case 11:
				ret.put("L_EYE_R", (int) val);
				continue;
			case 12:
				ret.put("L_EYE_G", (int) val);
				continue;
			case 13:
				ret.put("L_EYE_B", (int) val);
				continue;
			case 14:
				ret.put("MOUTH", (int) val);
				continue;
			}
		}
		return ret;
	}
}
