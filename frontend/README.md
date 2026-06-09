# Frontend

前端是一个无需构建工具的静态页面，可以直接打开 `index.html`，也可以通过任意静态文件服务访问。

## 目录结构

- `index.html`：页面结构和资源入口。
- `assets/css/styles.css`：页面样式。
- `assets/js/config.js`：接口地址、默认实体、默认关系、图谱颜色配置。
- `assets/js/state.js`：页面运行时状态。
- `assets/js/api.js`：后端接口请求。
- `assets/js/graph.js`：知识图谱渲染、居中、清空。
- `assets/js/ui.js`：页面事件绑定、表单、弹窗和抽取流程。
- `assets/js/app.js`：应用初始化入口。

脚本按 `config -> state -> api -> graph -> ui -> app` 的顺序加载，新增文件时请保持依赖方向清晰。
