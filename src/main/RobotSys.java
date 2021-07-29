package main;

import jp.vstone.RobotLib.CCommUMotion;
import jp.vstone.RobotLib.CRobotMem;
import jp.vstone.RobotLib.CRobotMotion;
import jp.vstone.RobotLib.CRobotPose;
import jp.vstone.RobotLib.CRobotUtil;
import jp.vstone.RobotLib.CSotaMotion;

public class RobotSys {

	public static CRobotMem mem;
	public static CRobotMotion motion;
	public static String LOCK_KEY = "local";

	public static void initialize() {
		mem = new CRobotMem();
		motion = getInstanceOfCRobotMotion();
	}

	public static void lockServoLedHandle() {
		if (Params.robotType.equals("CommU")) {
			Byte[] servoIds = new  Byte[]{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14};
			Byte[] ledIds   = new  Byte[]{0, 1, 2, 3, 4, 5, 6};
			motion.LockServoHandle(servoIds);
			motion.LockLEDHandle(ledIds);
		} else if (Params.robotType.equals("Sota")) {
			Byte[] servoIds = new  Byte[]{1, 2, 3, 4, 5, 6, 7, 8};
			Byte[] ledIds   = new  Byte[]{0, 1, 2, 8, 9, 10, 11, 12, 13};
			motion.LockServoHandle(servoIds);
			motion.LockLEDHandle(ledIds);
		} else if (Params.robotType.equals("Dog")) {
			Byte[] servoIds = new  Byte[]{1, 3, 5, 7, 8};
			Byte[] ledIds   = new  Byte[]{0, 1, 2};
			motion.LockServoHandle(servoIds);
			motion.LockLEDHandle(ledIds);
		}
	}

	public static void unLockServoLedHandle() {
		if (Params.robotType.equals("CommU")) {
			Byte[] servoIds = new  Byte[]{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14};
			Byte[] ledIds   = new  Byte[]{0, 1, 2, 3, 4, 5, 6};
			motion.UnLockServoHandle(servoIds);
			motion.UnLockLEDHandle(ledIds);
		} else if (Params.robotType.equals("Sota")) {
			Byte[] servoIds = new  Byte[]{1, 2, 3, 4, 5, 6, 7, 8};
			Byte[] ledIds   = new  Byte[]{0, 1, 2, 8, 9, 10, 11, 12, 13};
			motion.UnLockServoHandle(servoIds);
			motion.UnLockLEDHandle(ledIds);
		} else if (Params.robotType.equals("Dog")) {
			Byte[] servoIds = new  Byte[]{1, 3, 5, 7, 8};
			Byte[] ledIds   = new  Byte[]{0, 1, 2};
			motion.UnLockServoHandle(servoIds);
			motion.UnLockLEDHandle(ledIds);
		}
	}

	private static CRobotMotion getInstanceOfCRobotMotion() {
		if      (Params.robotType.equals("CommU")) return RobotSys.initCommU();
		else if (Params.robotType.equals("Sota"))  return RobotSys.initSota();
		else if (Params.robotType.equals("Dog"))   return RobotSys.initDog();
		else {
			System.err.println("RobotType is invalid. robotType=" + Params.robotType);
			return null;
		}
	}

	private static CRobotMotion initCommU() {
		CCommUMotion motion = new CCommUMotion(mem);
		if (mem.Connect()) {
			motion.InitRobot_CommU();
			motion.ServoOn();
			motion.LipSyncEnable(true);
			Byte[]  poseIds  = null, torqueIds  = null, ledIds  = null;
			Short[] poseVals = null, torqueVals = null, ledVals = null;
			poseIds    = new  Byte[]{    1,    2,    3,    4,    5,    6,    7,    8,    9,   10,   11,   12,   13,   14};
			poseVals   = new Short[]{    0,    0,  600,    0, -600,    0,    0,    0,    0,    0,    0,    0,    0,    0};
			torqueIds  = new  Byte[]{    1,    2,    3,    4,    5,    6,    7,    8,    9,   10,   11,   12,   13,   14};
			torqueVals = new Short[]{  100,  100,  100,  100,  100,  100,  100,  100,  100,  100,  100,  100,   50,   50};
			ledIds     = new  Byte[]{    0,    1,    2,    3,    4,    5,    6};
			ledVals    = new Short[]{    0,    0,    0,    0,    0,    0,    0};
			CRobotPose pose = new CRobotPose();
			pose.SetPose(poseIds, poseVals);
			pose.SetTorque(torqueIds, torqueVals);
			pose.SetLed(ledIds, ledVals);
			motion.play(pose, 1500);
			CRobotUtil.wait(1500);
			return motion;
		}
		else {
			System.err.println("The constructer could not connect to the robot memory. ");
			return null;
		}
	}

	private static CRobotMotion initSota() {
		CSotaMotion motion = new CSotaMotion(mem);
		if (mem.Connect()) {
			motion.InitRobot_Sota();
			motion.ServoOn();
			Byte[]  poseIds  = null, torqueIds  = null, ledIds  = null;
			Short[] poseVals = null, torqueVals = null, ledVals = null;
			poseIds    = new  Byte[]{    1,    2,    3,    4,    5,    6,    7,    8};
			poseVals   = new Short[]{    0, -900,    0,  900,    0,    0,    0,    0};
			torqueIds  = new  Byte[]{    1,    2,    3,    4,    5,    6,    7,    8};
			torqueVals = new Short[]{  100,  100,  100,  100,  100,  100,  100,  100};
			ledIds     = new  Byte[]{    0,    1,    2,    8,    9,   10,   11,   12,   13};
			ledVals    = new Short[]{    0,    0,    0,  255,  255,  255,  255,  255,  255};
			CRobotPose pose = new CRobotPose();
			pose.SetPose(poseIds, poseVals);
			pose.SetTorque(torqueIds, torqueVals);
			pose.SetLed(ledIds, ledVals);
			motion.play(pose, 1500);
			CRobotUtil.wait(1500);
			return motion;
		}
		else {
			System.err.println("The constructer could not connect to the robot memory. ");
			return null;
		}
	}

	private static CRobotMotion initDog() {
		CSotaMotion motion = new CSotaMotion(mem);
		if (mem.Connect()) {
			motion.InitRobot_Sota();
			motion.ServoOn();
			Byte[]  poseIds  = null, torqueIds  = null, ledIds  = null;
			Short[] poseVals = null, torqueVals = null, ledVals = null;
			poseIds    = new  Byte[]{    1,    3,    5,    7,    8};
			poseVals   = new Short[]{    0,    0,    0,    0,    0};
			torqueIds  = new  Byte[]{    1,    3,    5,    7,    8};
			torqueVals = new Short[]{  100,  100,  100,  100,  100};
			ledIds     = new  Byte[]{    0,    1,    2};
			ledVals    = new Short[]{    0,    0,    0};
			CRobotPose pose = new CRobotPose();
			pose.SetPose(poseIds, poseVals);
			pose.SetTorque(torqueIds, torqueVals);
			pose.SetLed(ledIds, ledVals);
			motion.play(pose, 1500);
			CRobotUtil.wait(1500);
			return motion;
		}
		else {
			System.err.println("The constructer could not connect to the robot memory. ");
			return null;
		}
	}

}
