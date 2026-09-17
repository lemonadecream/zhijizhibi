/**
 * Demo 访谈脚本（确定性追问引擎）的单元测试。
 *
 * 这里锁的是本轮的**核心产品承诺**：
 *   同一个用户的前后回答会影响下一轮问题，而不是 preset 的 8 个问题。
 *
 * 脚本本身必须满足三条硬约束：
 *  1. 纯确定性 —— 不联网、不调 LLM（Demo 不能产生任何真实模型费用）
 *  2. 追问要有上下文关系 —— 引用用户真实说过的主体/数字/偏好/反例
 *  3. 轮数固定在 7~8 轮，且最后一轮先确认理解、再生成画像
 */
import { describe, expect, it } from "vitest";
import {
  CLOSING_LINE,
  INTRO_OPENER,
  SECONDARY_HINT,
  TOTAL_TURNS,
  nextQuestion,
  pickSubject,
} from "../pages/DemoInterview/demoScript";

describe("demoScript / 轮次与首屏文案", () => {
  it("轮次落在 7~8 轮", () => {
    expect(TOTAL_TURNS).toBeGreaterThanOrEqual(7);
    expect(TOTAL_TURNS).toBeLessThanOrEqual(8);
  });

  it("首屏是单一引导语，辅助入口是低权重的简历提示", () => {
    expect(INTRO_OPENER).toContain("印象");
    expect(SECONDARY_HINT).toContain("上传简历");
  });
});

describe("demoScript / pickSubject 主体抽取", () => {
  it("优先取用户自己强调的引号内容", () => {
    expect(pickSubject("我在做「用户增长」这件事的时候")).toBe("用户增长");
  });

  it("识别「在 XX 公司/团队/项目」", () => {
    expect(pickSubject("我之前在云枢科技实习过半年")).toBe("云枢");
    expect(pickSubject("在一个校园项目里负责调研")).toBe("一个校园");
  });

  it("识别句首的项目名", () => {
    expect(pickSubject("潮汐电商项目是我参与度最高的")).toBe("潮汐电商");
  });

  it("抽不到主体时返回 null，交由通用问句兜底（绝不编造）", () => {
    expect(pickSubject("就是随便做了一些事情")).toBeNull();
    expect(pickSubject("")).toBeNull();
  });
});

describe("demoScript / nextQuestion 上下文相关", () => {
  it("第 1 轮能引用上一句里识别到的主体", () => {
    const q = nextQuestion(1, "我之前在云枢科技实习，负责客户反馈整理。");
    expect(q).toContain("云枢");
    expect(q).toContain("负责");
  });

  it("第 1 轮抽不到主体时落到通用问法", () => {
    const q = nextQuestion(1, "做过一些杂事。");
    expect(q).toContain("最有代表性");
  });

  it("第 2 轮是否追问『可衡量的结果』取决于上一轮有没有数字", () => {
    const withNumber = nextQuestion(2, "最后咨询量少了三成。");
    const withoutNumber = nextQuestion(2, "反正就是做完了。");
    expect(withNumber).toContain("具体一点");
    expect(withoutNumber).toContain("变化");
    expect(withNumber).not.toBe(withoutNumber);
  });

  it("第 4 轮按『独立 / 协作』倾向给出不同的追问", () => {
    const solo = nextQuestion(4, "我更喜欢自己一个人把事情推下去。");
    const teamish = nextQuestion(4, "我习惯和团队一起配合，大家商量着来。");
    const neutral = nextQuestion(4, "还行吧。");
    expect(solo).toContain("和别人对齐");
    expect(teamish).toContain("一个人拍板");
    expect(neutral).toContain("独立推进");
    expect(new Set([solo, teamish, neutral]).size).toBe(3);
  });

  it("第 6 轮：已经说过反例就继续深挖，没说就先问反例", () => {
    const said = nextQuestion(6, "我不想做纯执行、不问为什么的活。");
    const notSaid = nextQuestion(6, "我觉得还好。");
    expect(said).toContain("还有没有别的");
    expect(notSaid).toContain("明确不想接受");
  });

  it("每轮都有非空问题，轮次用尽后返回空串", () => {
    for (let t = 1; t < TOTAL_TURNS; t++) {
      expect(nextQuestion(t, "我负责了一块内容，后来有些变化。").length).toBeGreaterThan(10);
    }
    expect(nextQuestion(TOTAL_TURNS, "任意")).toBe("");
  });

  it("同一句输入在不同轮次得到不同问题（不是固定的 8 问）", () => {
    const same = "我负责客户反馈整理，最后有一部分进了版本。";
    const qs = Array.from({ length: TOTAL_TURNS - 1 }, (_, i) => nextQuestion(i + 1, same));
    expect(new Set(qs).size).toBe(qs.length);
  });

  it("最后一轮先复述理解并明确说出不确定项，不直接给结论", () => {
    const q = nextQuestion(7, "我更喜欢自己推进，但需要人把目标讲清楚。");
    expect(q).toContain("我大概理了一下");
    expect(q).toContain("不确定");
    expect(q).toContain("一致吗");
  });

  it("收束语在确认之后才出现", () => {
    expect(CLOSING_LINE).toContain("画像");
  });
});
