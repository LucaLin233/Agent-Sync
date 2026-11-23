import { defineSettings } from "@getpaseo/plugin";
import { z } from "zod";

export const SETTINGS_ID = "chinese-titles";

export const settingsSchema = z.object({
  autoNameProjects: z
    .boolean()
    .catch(true)
    .describe("为新登记的项目生成一次中文侧栏名称；只改显示覆盖，不改目录。"),
  autoNameWorkspaces: z
    .boolean()
    .catch(true)
    .describe("工作区收到首个真实任务时生成一次中文标题；只改显示覆盖，不改分支或目录。"),
  autoNameSessions: z
    .boolean()
    .catch(false)
    .describe("默认关闭。开启后新建普通会话收到首个真实任务时生成一次中文标题；请先关闭 Better Paseo 的自动优化新任务标题。"),
  provider: z
    .string()
    .trim()
    .max(120)
    .catch("")
    .describe("留空自动选择 daemon 已就绪的 Codex provider 或其别名（extends codex）。只允许 Codex 系列。"),
  model: z
    .string()
    .trim()
    .max(200)
    .catch("")
    .describe("留空使用所选 provider 的默认模型。"),
  thinkingOptionId: z
    .string()
    .trim()
    .max(80)
    .catch("")
    .describe("可留空，使用模型默认思考档位。"),
  projectMaxChars: z
    .number()
    .int()
    .min(4)
    .max(40)
    .catch(20)
    .describe("项目中文名称最大字符数。"),
  titleMaxChars: z
    .number()
    .int()
    .min(6)
    .max(60)
    .catch(28)
    .describe("工作区和会话中文标题最大字符数。"),
  paseoBin: z
    .string()
    .trim()
    .max(300)
    .catch("paseo")
    .describe("官方 paseo CLI 可执行文件；用于项目/会话更名的受信任回退。应能在 daemon 的 PATH 中运行。"),
});

export const CHINESE_TITLES_SETTINGS = defineSettings({
  id: SETTINGS_ID,
  scope: "host",
  version: 1,
  schema: settingsSchema,
});

export type ChineseTitlesSettings = z.output<typeof settingsSchema>;
