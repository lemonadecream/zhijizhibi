/**
 * Demo「AI 认识你」冷启动脚本的回归测试。
 *
 * 这个脚本必须满足三条硬约束：
 *  1. 纯确定性 —— 不联网、不调 LLM（Demo 不能产生任何真实模型费用）
 *  2. 追问要有上下文关系 —— 引用用户真实说过的主体/数字/偏好，而不是静态欢迎语
 *  3. 轮数固定 —— 3~4 轮内收束，符合"3~5 分钟看懂产品"的 Demo 目标
 */
import { describe, expect, it } from "vitest";
import {
  CLOSING_LINE,
  DEMO_GUIDES,
  TOTAL_TURNS,
  nextQuestion,
  pickSubject,
} from "../pages/DemoInterview/demoScript";

describe("Demo 冷启动脚本", () => {
  it("提供四个冷启动引导项，且每项都有开场白与预填示例", () => {
    expect(DEMO_GUIDES).toHaveLength(4);
    for (const g of DEMO_GUIDES) {
      expect(g.label.length).toBeGreaterThan(0);
      expect(g.opener.length).toBeGreaterThan(10);
      // 首屏要能"直接点击发送"，所以示例回答必须够具体
      expect(g.example.length).toBeGreaterThan(15);
    }
  });

  it("轮数固定为 3~4 轮，之后由收束语接手", () => {
    expect(TOTAL_TURNS).toBeGreaterThanOrEqual(3);
    expect(TOTAL_TURNS).toBeLessThanOrEqual(4);
    expect(nextQuestion(TOTAL_TURNS, "随便说点什么")).toBe("");
    expect(CLOSING_LINE.length).toBeGreaterThan(10);
  });

  describe("pickSubject：从自由文本里抽出可引用的主体", () => {
    it("优先取引号内容", () => {
      expect(pickSubject("我在「潮汐电商」做过内容运营")).toBe("潮汐电商");
    });

    it("识别「在 XX 公司/团队/项目」", () => {
      expect(pickSubject("我在这家公司实习过三个月")).toContain("这家");
      expect(pickSubject("在星野数据项目里负责调研")).toBe("星野数据");
    });

    it("识别句首的 XX 公司/项目", () => {
      expect(pickSubject("麦浪文化公司是我面试的第一家")).toBe("麦浪文化");
    });

    it("没有可引用主体时返回 null，而不是编造", () => {
      expect(pickSubject("就是做了很多事情")).toBeNull();
      expect(pickSubject("")).toBeNull();
    });
  });

  describe("nextQuestion：追问要引用上文，不是静态欢迎语", () => {
    it("第 1 轮引用用户提到的公司/项目", () => {
      const q = nextQuestion(1, "我在「潮汐电商」实习，做内容运营。");
      expect(q).toContain("潮汐电商");
      expect(q).toContain("负责");
    });

    it("第 1 轮没有主体时给通用但具体的追问", () => {
      const q = nextQuestion(1, "做了很多事情吧。");
      expect(q).not.toContain("undefined");
      expect(q).toContain("具体");
    });

    it("第 2 轮看到数字就追问量化结果，否则问变化", () => {
      expect(nextQuestion(2, "最后咨询量降低了三成")).toContain("具体");
      expect(nextQuestion(2, "就是做完了一个功能")).toContain("变化");
    });

    it("第 3 轮识别偏好类表达", () => {
      expect(nextQuestion(3, "我最看重能不能看到结果")).toContain("不妥协");
      expect(nextQuestion(3, "就正常干活")).toContain("最看重什么");
    });

    it("同一句输入在不同轮次得到不同追问（说明是轮次驱动的多轮，不是复读）", () => {
      const text = "我在潮汐电商实习";
      expect(nextQuestion(1, text)).not.toBe(nextQuestion(2, text));
      expect(nextQuestion(2, text)).not.toBe(nextQuestion(3, text));
    });
  });
});
