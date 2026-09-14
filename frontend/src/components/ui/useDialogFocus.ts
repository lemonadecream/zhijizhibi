import { useEffect, useRef } from "react";

/**
 * 弹层（Modal / Drawer）的键盘焦点管理：
 *  - 打开时把焦点移入弹层第一个可聚焦元素；
 *  - Tab / Shift+Tab 在弹层内循环（焦点陷阱，防止焦点逃到被遮罩的页面）；
 *  - 关闭时把焦点还原到打开前的元素。
 * 与各组件已有的 Esc 关闭配合，构成完整的键盘可达性。
 */
export function useDialogFocus(open: boolean, ref: React.RefObject<HTMLElement | null>) {
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = (document.activeElement as HTMLElement | null) ?? null;

    const focusables = () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        ) ?? []
      ).filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);

    focusables()[0]?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !ref.current) return;
      const list = focusables();
      if (list.length === 0) return;
      const first = list[0]!;
      const last = list[list.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      restoreRef.current?.focus?.();
    };
  }, [open, ref]);
}
