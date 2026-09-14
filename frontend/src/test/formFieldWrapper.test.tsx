/**
 * Textarea / Input 的 DOM 契约测试。
 *
 * 背景（Explore「AI 偏好输入区」宽度 bug 的根因）：
 * 这两个组件会把控件包一层 `<div class="field">`，所以当它们放在 flex 行内时，
 * **真正参与 flex 布局的是 .field 这个 wrapper，不是里面的 .textarea / .input**。
 * 如果 CSS 写 `.xxx .textarea { flex: 1 }`，规则会落在一个"不是 flex item"的元素上而静默失效，
 * 表现为输入框塌成浏览器默认宽度（约 200px），右侧留一大片空白。
 *
 * 这组测试把"wrapper 必须存在且是第一层"这个前提钉住：一旦组件结构变了，
 * 依赖它的 CSS 选择器就会失效，这里会第一时间报错，而不是等到有人截图才发现。
 */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Input from "../components/ui/Input";
import Textarea from "../components/ui/Textarea";

describe("表单组件的 wrapper 契约（CSS flex 选择器依赖它）", () => {
  it("Textarea 渲染为 .field > textarea.textarea", () => {
    const { container } = render(<Textarea defaultValue="" />);
    const wrapper = container.firstElementChild as HTMLElement;

    expect(wrapper).toBeInstanceOf(HTMLDivElement);
    expect(wrapper.classList.contains("field")).toBe(true);
    expect(wrapper.children).toHaveLength(1);

    const area = wrapper.firstElementChild as HTMLElement;
    expect(area.tagName).toBe("TEXTAREA");
    expect(area.classList.contains("textarea")).toBe(true);
  });

  it("Input 渲染为 .field > input.input", () => {
    const { container } = render(<Input defaultValue="" />);
    const wrapper = container.firstElementChild as HTMLElement;

    expect(wrapper.classList.contains("field")).toBe(true);
    const input = wrapper.firstElementChild as HTMLElement;
    expect(input.tagName).toBe("INPUT");
    expect(input.classList.contains("input")).toBe(true);
  });

  it("传入 className 作用在控件本身，而 wrapper 依然是 .field（CSS 选择器不会错位）", () => {
    const { container } = render(<Textarea className="custom-x" defaultValue="" />);
    const wrapper = container.firstElementChild as HTMLElement;

    expect(wrapper.classList.contains("field")).toBe(true);
    expect(wrapper.classList.contains("custom-x")).toBe(false);
    expect((wrapper.firstElementChild as HTMLElement).classList.contains("custom-x")).toBe(true);
  });
});
