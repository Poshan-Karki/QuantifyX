import React, { useLayoutEffect, useRef } from 'react';
import { createChart, ColorType, CandlestickSeries, LineSeries } from 'lightweight-charts';

const Chart = ({ data }) => {
    const chartContainerRef = useRef(null);
    const chartInstance = useRef(null);

    useLayoutEffect(() => {
        if (!chartContainerRef.current || !data?.ohlc?.length) return;

        const container = chartContainerRef.current;
        container.innerHTML = ''; 

        try {
            const chart = createChart(container, {
                width: container.clientWidth,
                height: 450,
                layout: {
                    background: { type: ColorType.Solid, color: '#050505' },
                    textColor: '#d1d4dc',
                },
                rightPriceScale: {
                    autoScale: true,
                    
                    scaleMargins: {
                        top: 0.1, 
                        bottom: 0.2, 
                    },
                },
                timeScale: {
                    timeVisible: true,
                
                    rightOffset: 5,
                },
            });
            chartInstance.current = chart;

            const candlestickSeries = chart.addSeries(CandlestickSeries, {
                upColor: '#10b981', 
                downColor: '#ef4444', 
                borderVisible: false,
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
            });

            const processedOhlc = data.ohlc.map(d => ({
                time: d.time,
                open: Number(d.open),
                high: Number(d.high),
                low: Number(d.low),
                close: Number(d.close),
            })).sort((a, b) => (a.time > b.time ? 1 : -1));

            candlestickSeries.setData(processedOhlc);
        
       


            
            if (data.indicators) {
                Object.entries(data.indicators).forEach(([name, values], index) => {
                    const lineSeries = chart.addSeries(LineSeries, {
                        color: ['#6366f1', '#f59e0b','#10b981'][index] ?? '#94a3b8',
                        lineWidth: 2,
                    });
                    const lineData = values.map((val, i) => ({
                        time: processedOhlc[i]?.time,
                        value: Number(val)
                    })).filter(v => v.time && !isNaN(v.value));
                    lineSeries.setData(lineData);
                });
            }

            chart.timeScale().fitContent();

        } catch (err) {
            console.error("Chart Error:", err);
        }

        const handleResize = () => {
            if (chartInstance.current) {
                chartInstance.current.applyOptions({ width: container.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);
        return () => {
            window.removeEventListener('resize', handleResize);
            if (chartInstance.current) chartInstance.current.remove();
        };
    }, [data]);

    return (
        <div ref={chartContainerRef} style={{ width: '100%', height: '450px' }} />
    );
};

export default Chart;