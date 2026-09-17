"""Render recorded metric flight convergence; does not connect to a vehicle."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main(folder):
    records=[json.loads(line) for line in (folder/'decisions.jsonl').read_text().splitlines()]
    trials=sorted({r['trial'] for r in records if r['phase']=='vision'})
    if not trials: raise ValueError('no vision cycles recorded')
    frames=[f for r in records if r['phase']=='vision' for f in r['frames']
            if 'nearby_truth' in f]
    exact_truth=bool(frames) and all(
        f['nearby_truth'].get('time_alignment')
        =='gazebo_simulation_timestamp' for f in frames)
    timing_note=(
        '图像与Gazebo评估真值按同一仿真时间戳对齐；PX4姿态和高度按主机接收'
        '时钟对图像传输回调时刻插值。Gazebo真值不输入控制。'
        if exact_truth else
        '时间匹配为悬停下的近似接收时刻。PX4姿态和高度用于投影；'
        'Gazebo真值只作评估和初始地面高程标定。')
    fig,axes=plt.subplots(len(trials),2,figsize=(11,3.6*len(trials)),squeeze=False)
    report=['# 米制视觉闭环飞行记录','',timing_note,'']
    for row,trial in enumerate(trials):
        points=[r for r in records if r['phase']=='vision' and r['trial']==trial]
        valid=[r for r in points if r['accepted']]
        for axis,key,true_key,label,threshold in [(axes[row,0],'lateral_error_m','lateral_m','Track-relative lateral (m)',.07),
                                                  (axes[row,1],'heading_error_deg','heading_deg','Track-relative heading (deg)',2)]:
            axis.plot([r['cycle'] for r in points],[r['truth'][true_key] for r in points],'-o',label='Gazebo truth')
            axis.plot([r['cycle'] for r in valid],[r['estimate'][key] for r in valid],'--x',label='YOLO + PX4 projection')
            axis.axhspan(-threshold,threshold,alpha=.12,color='green')
            axis.set(title=f'Trial {trial}: {label}',xlabel='Recognition cycle')
            axis.grid(alpha=.3); axis.legend()
        report.append(f'## 工况 {trial}')
        report.append('')
        report.append(f'识别有效 {len(valid)}/{len(points)} 轮。')
        if valid:
            a,b=valid[0],valid[-1]
            report.append(f"实际横向偏差 {a['truth']['lateral_m']:+.3f} → {b['truth']['lateral_m']:+.3f} m；实际航向偏差 {a['truth']['heading_deg']:+.2f} → {b['truth']['heading_deg']:+.2f}°。")
            report.append(f"视觉横向偏差 {a['estimate']['lateral_error_m']:+.3f} → {b['estimate']['lateral_error_m']:+.3f} m；视觉航向偏差 {a['estimate']['heading_error_deg']:+.2f} → {b['estimate']['heading_error_deg']:+.2f}°。")
            lat_mae=sum(abs(r['estimate']['lateral_error_m']-r['truth']['lateral_m']) for r in valid)/len(valid)
            yaw_mae=sum(abs(r['estimate']['heading_error_deg']-r['truth']['heading_deg']) for r in valid)/len(valid)
            alignment='同一Gazebo仿真时间戳' if exact_truth else '近似时间对齐'
            report.append(f'与真值的平均绝对差：横偏 {lat_mae:.3f} m，航向 {yaw_mae:.2f}°（{alignment}）。')
            pulses=sum(r['command']['forward_m_s']>0 for r in valid)
            report.append(f'已记录前进指令 {pulses} 次；是否完整完成脉冲以 summary.json 为准。')
        report.append('')
    fig.tight_layout(); fig.savefig(folder/'convergence.png',dpi=150); plt.close(fig)
    errors=[r['message'] for r in records if r['phase']=='error']
    if frames:
        height_errors=[abs(f['state']['body_agl_m']
                           -f['nearby_truth']['body_above_rail_m'])
                       for f in frames]
        truth_timing='同仿真时刻' if exact_truth else '邻近时刻'
        report += ['## 高度与时间诊断','',
                   (f'PX4投影高度与{truth_timing}Gazebo真值的绝对差：平均 '
                    f'{sum(height_errors)/len(height_errors):.3f} m，最大 '
                    f'{max(height_errors):.3f} m。')]
        offsets=[abs(f['nearby_truth']['query_offset_from_frame_s'])
                 for f in frames
                 if 'query_offset_from_frame_s' in f['nearby_truth']]
        exact=sum(f['nearby_truth'].get('time_alignment')
                  =='gazebo_simulation_timestamp' for f in frames)
        if offsets:
            report += [(f'真值查询中点距图像文件时刻：平均 '
                        f'{sum(offsets)/len(offsets):.3f} s，最大 '
                        f'{max(offsets):.3f} s。')]
        if exact:
            report += [f'{exact}/{len(frames)}帧的评估真值按Gazebo仿真时间戳插值。']
        report.append('')
    report += ['## 结束状态','',f"降落确认：{any(r['phase']=='landed' for r in records)}。",f'异常记录：{errors}。',
               '', '末轮数值来自最后一次观测，不代表降落后状态。测试初始化扰动单独记录，不计入视觉纠偏。']
    (folder/'README.md').write_text('\n'.join(report),encoding='utf-8')
    print('\n'.join(report))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('folder',type=Path)
    main(parser.parse_args().folder)
