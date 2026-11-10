/* 06 - Reporting views. The Excel report reads these. */
USE LakesideHospital;
GO

/* One row per account (= admission): what was charged, who owes what, what has been paid. */
CREATE OR ALTER VIEW reporting.vw_AccountBalance
AS
WITH Charged AS (
    SELECT AdmissionKey,
           SUM(Amount)        AS TotalCharged,
           SUM(FunderAmount)  AS FunderLiable,
           SUM(PatientAmount) AS PatientLiable
    FROM   core.FactCharge
    GROUP BY AdmissionKey
),
Paid AS (
    SELECT AdmissionKey,
           SUM(CASE WHEN PayerType = 'Funder'  THEN Amount ELSE 0 END) AS FunderPaid,
           SUM(CASE WHEN PayerType = 'Patient' THEN Amount ELSE 0 END) AS PatientPaid
    FROM   core.FactPayment
    GROUP BY AdmissionKey
)
SELECT a.AdmissionID                          AS AccountNo,
       p.PatientID,
       p.FullName                             AS PatientName,
       fu.FunderName,
       fu.FunderType,
       w.WardName,
       dr.DoctorName,
       dr.Speciality,
       a.AdmissionType,
       a.DiagnosisGroup,
       CAST(a.AdmitDateTime AS date)          AS AdmitDate,
       CAST(a.DischargeDateTime AS date)      AS DischargeDate,
       a.LengthOfStayDays,
       x.TotalCharged,
       x.FunderLiable,
       x.FunderPaid,
       x.FunderLiable - x.FunderPaid          AS FunderOutstanding,
       x.PatientLiable,
       x.PatientPaid,
       x.PatientLiable - x.PatientPaid        AS PatientOutstanding,
       x.TotalCharged - x.FunderPaid - x.PatientPaid AS TotalOutstanding,
       CASE WHEN a.DischargeDateTime IS NULL THEN 'In hospital'
            WHEN x.TotalCharged - x.FunderPaid - x.PatientPaid <= 0 THEN 'Settled'
            WHEN x.FunderPaid + x.PatientPaid = 0 THEN 'Unpaid'
            ELSE 'Part paid' END              AS AccountStatus
FROM   core.FactAdmission AS a
JOIN   core.DimPatient    AS p  ON p.PatientKey = a.PatientKey
JOIN   core.DimFunder     AS fu ON fu.FunderKey = a.FunderKey
JOIN   core.DimWard       AS w  ON w.WardKey    = a.WardKey
JOIN   core.DimDoctor     AS dr ON dr.DoctorKey = a.DoctorKey
LEFT JOIN Charged AS c  ON c.AdmissionKey  = a.AdmissionKey
LEFT JOIN Paid    AS pd ON pd.AdmissionKey = a.AdmissionKey
CROSS APPLY (SELECT COALESCE(c.TotalCharged, 0)  AS TotalCharged,
                    COALESCE(c.FunderLiable, 0)  AS FunderLiable,
                    COALESCE(c.PatientLiable, 0) AS PatientLiable,
                    COALESCE(pd.FunderPaid, 0)   AS FunderPaid,
                    COALESCE(pd.PatientPaid, 0)  AS PatientPaid) AS x;
GO

CREATE OR ALTER VIEW reporting.vw_FunderSummary
AS
SELECT FunderName,
       FunderType,
       COUNT(*)                AS Accounts,
       SUM(TotalCharged)       AS TotalCharged,
       SUM(FunderLiable)       AS FunderLiable,
       SUM(FunderPaid)         AS FunderPaid,
       SUM(FunderOutstanding)  AS FunderOutstanding,
       SUM(PatientLiable)      AS PatientLiable,
       SUM(PatientPaid)        AS PatientPaid,
       SUM(PatientOutstanding) AS PatientOutstanding
FROM   reporting.vw_AccountBalance
GROUP BY FunderName, FunderType;
GO

/* Bed use per ward per month. Every accommodation charge line is one bed for one night,
   so counting them gives the bed-days used. */
CREATE OR ALTER VIEW reporting.vw_WardOccupancy
AS
WITH Months AS (
    SELECT CalendarYear, MonthNumber, MonthName, COUNT(*) AS DaysInMonth
    FROM   core.DimDate
    GROUP BY CalendarYear, MonthNumber, MonthName
),
Used AS (
    SELECT a.WardKey, d.CalendarYear, d.MonthNumber,
           COUNT(*)                       AS BedDaysUsed,
           COUNT(DISTINCT c.AdmissionKey) AS Admissions
    FROM   core.FactCharge    AS c
    JOIN   core.FactAdmission AS a ON a.AdmissionKey = c.AdmissionKey
    JOIN   core.DimDate       AS d ON d.DateKey      = c.ServiceDateKey
    WHERE  c.ChargeSource = 'Accommodation'
    GROUP BY a.WardKey, d.CalendarYear, d.MonthNumber
)
SELECT w.WardCode,
       w.WardName,
       w.WardType,
       w.BedCount,
       m.CalendarYear,
       m.MonthNumber,
       m.MonthName,
       u.Admissions,
       u.BedDaysUsed,
       w.BedCount * m.DaysInMonth AS BedDaysAvailable,
       CAST(100.0 * u.BedDaysUsed / (w.BedCount * m.DaysInMonth) AS decimal(5,1)) AS OccupancyPct
FROM   Used AS u
JOIN   core.DimWard AS w ON w.WardKey = u.WardKey
JOIN   Months       AS m ON m.CalendarYear = u.CalendarYear AND m.MonthNumber = u.MonthNumber;
GO

CREATE OR ALTER VIEW reporting.vw_RevenueByCategory
AS
SELECT d.CalendarYear,
       d.MonthNumber,
       d.MonthName,
       t.Category,
       COUNT(*)             AS ChargeLines,
       SUM(c.Amount)        AS TotalCharged,
       SUM(c.FunderAmount)  AS FunderLiable,
       SUM(c.PatientAmount) AS PatientLiable
FROM   core.FactCharge AS c
JOIN   core.DimDate    AS d ON d.DateKey   = c.ServiceDateKey
JOIN   core.DimTariff  AS t ON t.TariffKey = c.TariffKey
GROUP BY d.CalendarYear, d.MonthNumber, d.MonthName, t.Category;
GO

CREATE OR ALTER VIEW reporting.vw_DoctorActivity
AS
SELECT DoctorName,
       Speciality,
       COUNT(*)                                             AS Admissions,
       CAST(AVG(1.0 * LengthOfStayDays) AS decimal(5,1))    AS AvgLengthOfStayDays,
       SUM(TotalCharged)                                    AS TotalCharged
FROM   reporting.vw_AccountBalance
GROUP BY DoctorName, Speciality;
GO
