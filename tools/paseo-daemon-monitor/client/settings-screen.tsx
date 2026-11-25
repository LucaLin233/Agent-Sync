import type { PluginSurfaceProps } from "@getpaseo/plugin/client";
import { useSettings } from "@getpaseo/plugin/client";
import { SettingsCard, SettingsSection, SettingsSelect, SettingsSwitch } from "@getpaseo/plugin/client/ui";
import { Pressable, Text, View } from "react-native";
import { INTERVAL_OPTIONS, monitorSettings, parseInterval } from "../shared/settings.ts";

/**
 * Settings → Plugins → 宿主机资源. Values live in the selected daemon's
 * host-scoped document, so every client connected to that daemon sees the same
 * cadence and footer switch.
 */
export function SettingsScreen({ theme }: PluginSurfaceProps) {
  const colors = theme.colors;
  const state = useSettings(monitorSettings);

  if (state.status === "loading") {
    return (
      <SettingsCard>
        <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>正在读取此 daemon 的插件设置…</Text>
      </SettingsCard>
    );
  }

  if (state.status === "error" || state.status === "invalid") {
    return (
      <SettingsCard>
        <View style={{ gap: 8 }}>
          <Text style={{ color: colors.statusDanger, fontSize: 13, fontWeight: "600" }}>无法读取宿主机资源设置</Text>
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            {state.status === "invalid"
              ? "已保存的设置不符合当前版本格式，可重试读取或恢复默认值。"
              : "请确认当前 daemon 连接正常后重试。"}
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => void state.reload()}
            style={({ pressed }) => ({
              alignSelf: "flex-start",
              paddingHorizontal: 10,
              paddingVertical: 6,
              borderRadius: 6,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: pressed ? colors.surface2 : colors.surface1,
            })}
          >
            <Text style={{ color: colors.foreground, fontSize: 12, fontWeight: "600" }}>重试</Text>
          </Pressable>
        </View>
      </SettingsCard>
    );
  }

  const values = state.values;
  const failure = state.saveError ? "设置未保存，请重试。" : null;

  return (
    <View style={{ gap: 12 }}>
      <SettingsSection
        title="作用范围"
        info={
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            调整为当前 daemon 安装（host）的设置，影响所有连接该 daemon 的客户端；其他主机各有自己的设置。
          </Text>
        }
      >
        <SettingsCard>
          <View style={{ gap: 4 }}>
            <Text style={{ color: colors.foreground, fontSize: 13, fontWeight: "600" }}>宿主机资源</Text>
            <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
              数据由 daemon 读取所在主机的 CPU、内存与磁盘，设置只影响采样节奏和底部一行，不改动主机配置。
            </Text>
          </View>
        </SettingsCard>
      </SettingsSection>

      <SettingsSection title="采样">
        <SettingsSelect
          label="采样间隔"
          hint="CPU、内存与网速的刷新节拍；磁盘仍约 30 秒刷新一次。切换后立即生效，无需重载插件。"
          value={String(values.intervalMs)}
          options={INTERVAL_OPTIONS}
          disabled={state.saving}
          onValueChange={(next) => {
            void state.save({ ...values, intervalMs: parseInterval(next) }, state.revision);
          }}
        />
        <SettingsSwitch
          label="在底栏显示网速"
          hint="关闭只影响侧栏底部一行；详情中的下行、上行与曲线仍然显示。侧栏太窄时也会自动收起。"
          value={values.showNetworkInFooter}
          disabled={state.saving}
          onValueChange={(next) => {
            void state.save({ ...values, showNetworkInFooter: next }, state.revision);
          }}
        />
      </SettingsSection>

      {state.saving ? (
        <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>正在保存…</Text>
      ) : failure ? (
        <Text style={{ color: colors.statusDanger, fontSize: 12 }}>{failure}</Text>
      ) : null}
    </View>
  );
}
