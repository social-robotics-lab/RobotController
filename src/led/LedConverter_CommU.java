package led;

import java.util.HashMap;
import java.util.Map;

import org.json.JSONObject;

public class LedConverter_CommU {

	private static final Map<String, Byte> map = new HashMap<String, Byte>() {
		{
			put("PWR_BTN_R", (byte) 0);
			put("PWR_BTN_G", (byte) 1);
			put("PWR_BTN_B", (byte) 2);
			put("BODY_R",    (byte) 3);
			put("BODY_G",    (byte) 4);
			put("BODY_B",    (byte) 5);
			put("L_CHEEK",   (byte) 6);
			put("R_CHEEK",   (byte) 7);
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
			case 3:
				ret.put("BODY_R", (int) val);
				continue;
			case 4:
				ret.put("BODY_G", (int) val);
				continue;
			case 5:
				ret.put("BODY_B", (int) val);
				continue;
			case 6:
				ret.put("L_CHEEK", (int) val);
				continue;
			case 7:
				ret.put("R_CHEEK", (int) val);
				continue;
			}
		}
		return ret;
	}

}
