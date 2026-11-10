/* 08 - Queries I used to look at the data once it was loaded. */
USE LakesideHospital;
GO

-- 1. Debtors age analysis: how old is the money still owed on discharged accounts?
DECLARE @AsAt date = (SELECT MAX(d.FullDate)
                      FROM core.FactPayment AS p
                      JOIN core.DimDate AS d ON d.DateKey = p.PaymentDateKey);

WITH Aged AS (
    SELECT FunderType, FunderOutstanding, PatientOutstanding,
           CASE WHEN DATEDIFF(DAY, DischargeDate, @AsAt) <= 30 THEN '1) 0-30 days'
                WHEN DATEDIFF(DAY, DischargeDate, @AsAt) <= 60 THEN '2) 31-60 days'
                WHEN DATEDIFF(DAY, DischargeDate, @AsAt) <= 90 THEN '3) 61-90 days'
                ELSE '4) Over 90 days' END AS AgeBand
    FROM   reporting.vw_AccountBalance
    WHERE  DischargeDate IS NOT NULL
      AND  TotalOutstanding > 0
)
SELECT AgeBand,
       COUNT(*)                AS Accounts,
       SUM(FunderOutstanding)  AS OwedByFunders,
       SUM(PatientOutstanding) AS OwedByPatients
FROM   Aged
GROUP BY AgeBand
ORDER BY AgeBand;

-- 2. What does a stay cost? Average bill and length of stay per diagnosis group
SELECT DiagnosisGroup,
       COUNT(*)                                          AS Admissions,
       CAST(AVG(1.0 * LengthOfStayDays) AS decimal(5,1)) AS AvgStayDays,
       CAST(AVG(TotalCharged) AS decimal(12,2))          AS AvgBill,
       MAX(TotalCharged)                                 AS HighestBill
FROM   reporting.vw_AccountBalance
WHERE  DischargeDate IS NOT NULL
GROUP BY DiagnosisGroup
ORDER BY AvgBill DESC;

-- 3. Where does the money come from? Share of revenue per charge category
SELECT Category,
       SUM(TotalCharged) AS TotalCharged,
       CAST(100.0 * SUM(TotalCharged) / SUM(SUM(TotalCharged)) OVER () AS decimal(5,1)) AS SharePct
FROM   reporting.vw_RevenueByCategory
GROUP BY Category
ORDER BY TotalCharged DESC;

-- 4. Did the 1 July increase come through? Average accommodation rate charged per ward, before and after
SELECT w.WardName,
       CAST(AVG(CASE WHEN d.FullDate <  '2025-07-01' THEN c.Rate END) AS decimal(10,2)) AS AvgRateBeforeJuly,
       CAST(AVG(CASE WHEN d.FullDate >= '2025-07-01' THEN c.Rate END) AS decimal(10,2)) AS AvgRateFromJuly
FROM   core.FactCharge    AS c
JOIN   core.FactAdmission AS a ON a.AdmissionKey = c.AdmissionKey
JOIN   core.DimWard       AS w ON w.WardKey      = a.WardKey
JOIN   core.DimDate       AS d ON d.DateKey      = c.ServiceDateKey
WHERE  c.ChargeSource = 'Accommodation'
GROUP BY w.WardName;

-- 5. Readmissions: patients admitted again within 30 days of their previous discharge
WITH Stays AS (
    SELECT PatientID, PatientName, AccountNo, AdmitDate, DiagnosisGroup,
           LAG(DischargeDate) OVER (PARTITION BY PatientID ORDER BY AdmitDate) AS PreviousDischarge
    FROM   reporting.vw_AccountBalance
)
SELECT PatientID, PatientName, AccountNo, DiagnosisGroup, PreviousDischarge, AdmitDate,
       DATEDIFF(DAY, PreviousDischarge, AdmitDate) AS DaysSinceLastStay
FROM   Stays
WHERE  DATEDIFF(DAY, PreviousDischarge, AdmitDate) BETWEEN 0 AND 30
ORDER BY DaysSinceLastStay;

-- 6. Busiest and quietest month per ward
WITH Ranked AS (
    SELECT WardName, MonthName, OccupancyPct,
           RANK() OVER (PARTITION BY WardCode ORDER BY OccupancyPct DESC) AS Busiest,
           RANK() OVER (PARTITION BY WardCode ORDER BY OccupancyPct ASC)  AS Quietest
    FROM   reporting.vw_WardOccupancy
)
SELECT WardName, MonthName, OccupancyPct,
       CASE WHEN Busiest = 1 THEN 'Busiest' ELSE 'Quietest' END AS Which
FROM   Ranked
WHERE  Busiest = 1 OR Quietest = 1
ORDER BY WardName, OccupancyPct DESC;

-- 7. Theatre use per month (minutes are the quantity on the theatre tariffs)
SELECT d.CalendarYear, d.MonthNumber, d.MonthName,
       COUNT(*)                                  AS TheatreSessions,
       SUM(c.Quantity)                           AS TheatreMinutes,
       CAST(SUM(c.Quantity) / 60.0 AS decimal(8,1)) AS TheatreHours,
       SUM(c.Amount)                             AS TheatreRevenue
FROM   core.FactCharge AS c
JOIN   core.DimTariff  AS t ON t.TariffKey = c.TariffKey
JOIN   core.DimDate    AS d ON d.DateKey   = c.ServiceDateKey
WHERE  t.Category = 'Theatre'
GROUP BY d.CalendarYear, d.MonthNumber, d.MonthName
ORDER BY d.CalendarYear, d.MonthNumber;

-- 8. The 10 biggest unpaid patient balances
SELECT TOP (10) AccountNo, PatientName, FunderName, DischargeDate, PatientLiable, PatientPaid, PatientOutstanding
FROM   reporting.vw_AccountBalance
WHERE  DischargeDate IS NOT NULL
ORDER BY PatientOutstanding DESC;
GO
