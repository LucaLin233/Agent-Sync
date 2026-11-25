import type { PluginSurfaceProps } from "@getpaseo/plugin/client";
import { useSettings } from "@getpaseo/plugin/client";
import { SettingsAction, SettingsCard, SettingsRow, SettingsSection, SettingsSelect, SettingsSwitch } from "@getpaseo/plugin/client/ui";
import { INTERVAL_OPTIONS, monitorSettings, parseInterval } from "../shared/settings.ts";

/**
 * Settings → Plugins → 宿主机资源. Values live in the selected daemon's
 * host-scoped document, so every client connected to that daemon sees the same
 * cadence and footer switch.
 *
 * Everything is built from the native settings primitives: `SettingsSection`
 * renders the heading, `SettingsCard` gives each child the standard row
 * padding/border, and `SettingsSelect`/`SettingsSwitch`/`SettingsAction` keep
 * the label on the left and the control on the right. Hand-built rows inside a
 * card lose that padding, which is what pushed the previous copy to the edge.
 */
export function SettingsScreen(_props: PluginSurfaceProps) {
  const state = useSettings(monitorSettings);

  if (state.status === "loading") {
    return (
      <SettingsSection title="宿主机资源">
        <SettingsCard>
          <SettingsRow label="读取设置…" hint="正在向当前 daemon 请求插件设置。" />
        </SettingsCard>
      </SettingsSection>
    );
  }

  if (state.status === "error" || state.status === "invalid") {
    return (
      <SettingsSection title="宿主机资源">
        <SettingsCard>
          <SettingsRow
            label="无法读取设置"
            hint={
              state.status === "invalid"
                ? "已保存的设置不符合当前版本格式，可重试读取。"
                : "请确认当前 daemon 连接正常后重试。"
            }
            error={state.status === "invalid" ? "设置格式无效。" : "读取失败。"}
          />
          <SettingsAction
            label="重新读取"
            hint="重新向当前 daemon 请求设置。"
            actionLabel="重试"
            onPress={() => void state.reload()}
          />
        </SettingsCard>
      </SettingsSection>
    );
  }

  const values = state.values;

  return (
    <SettingsSection title="宿主机资源">
      <SettingsCard>
        <SettingsSelect
          label="采样间隔"
          hint="仅作用于当前 daemon 安装，连接它的客户端共用；磁盘仍约 30 秒刷新一次。"
          value={String(values.intervalMs)}
          options={INTERVAL_OPTIONS}
          disabled={state.saving}
          onValueChange={(next) => {
            void state.save({ ...values, intervalMs: parseInterval(next) }, state.revision);
          }}
        />
        <SettingsSwitch
          label="在底栏显示网速"
          hint="关闭只影响侧栏底部一行；详情与曲线仍显示，侧栏过窄时也会自动收起。"
          value={values.showNetworkInFooter}
          disabled={state.saving}
          onValueChange={(next) => {
            void state.save({ ...values, showNetworkInFooter: next }, state.revision);
          }}
        />
        {state.saving ? <SettingsRow label="正在保存…" hint="等待当前 daemon 确认新设置。" /> : null}
        {state.saveError ? (
          <SettingsRow label="设置未保存" error="更改尚未作用于当前 daemon，请重试。" />
        ) : null}
      </SettingsCard>
    </SettingsSection>
  );
}
