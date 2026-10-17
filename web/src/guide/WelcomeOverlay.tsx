import { useState } from "react";
import { readStorage, writeStorage } from "./storage";

const SLIDES = [
  {
    title: "这是什么?",
    body: "Axiom 是一套工业算法评估工作台:把算法放进一条从数学到现场的验证流水线,每层结论都以带证据等级、可审计的「声明」发布,而不是一句模糊的“效果不错”。",
  },
  {
    title: "怎么用?",
    body: "每个实验台都是同一个节奏:左侧选场景(内置正例与反例)→ 运行 → 读结论徽章,再到右侧核对声明与执行链。所有图表都可以悬停查看数值。",
  },
  {
    title: "从哪开始?",
    body: "先在默认首页「载入回归示例」跑一次 A/B 比较;想看全貌就点顶部的「实验路径」,八步流水线里随便跳,每个台都有一句人话说明。",
  },
];

const STORAGE_KEY = "axiom-welcomed";

export function WelcomeOverlay() {
  const [visible, setVisible] = useState(() => readStorage(STORAGE_KEY) !== "1");
  const [slide, setSlide] = useState(0);

  if (!visible) return null;

  const finish = () => {
    writeStorage(STORAGE_KEY, "1");
    setVisible(false);
  };

  const current = SLIDES[slide]!;

  return (
    <div className="guide-overlay" role="presentation">
      <div className="guide-welcome" role="dialog" aria-modal="true" aria-label="使用引导">
        <span className="guide-stage">使用引导 · {slide + 1}/{SLIDES.length}</span>
        <h2>{current.title}</h2>
        <p>{current.body}</p>
        <div className="guide-welcome-actions">
          <span className="guide-dots" aria-hidden="true">
            {SLIDES.map((item, index) => <i key={item.title} className={index === slide ? "active" : ""} />)}
          </span>
          {slide < SLIDES.length - 1 ? (
            <>
              <button type="button" className="button button-secondary" onClick={finish}>跳过</button>
              <button type="button" className="button button-primary" onClick={() => setSlide((value) => value + 1)}>下一张</button>
            </>
          ) : (
            <button type="button" className="button button-primary" onClick={finish}>开始体验</button>
          )}
        </div>
      </div>
    </div>
  );
}
