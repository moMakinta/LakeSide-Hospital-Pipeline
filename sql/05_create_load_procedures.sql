/* 05 - Procs that load core from landing.
   Needs SQL Server 2016 SP1+ because of CREATE OR ALTER.
   Running them twice on the same landing data should not change anything. */
USE LakesideHospital;
GO

/* Wards, doctors, funders and patients. Changes just overwrite the old values. */
CREATE OR ALTER PROCEDURE core.usp_LoadDimensions
    @Rows int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @Rows = 0;

    -- the EXISTS / EXCEPT part checks if any column changed and it handles NULLs,
    -- which a normal <> comparison doesn't

    -- wards
    UPDATE d
    SET    WardName = s.WardName, WardType = s.WardType, BedCount = s.BedCount,
           AccommodationTariffCode = s.AccommodationTariffCode
    FROM   core.DimWard AS d
    JOIN   landing.Ward AS s ON s.WardCode = d.WardCode
    WHERE  EXISTS (SELECT s.WardName, s.WardType, s.BedCount, s.AccommodationTariffCode
                   EXCEPT
                   SELECT d.WardName, d.WardType, d.BedCount, d.AccommodationTariffCode);
    SET @Rows += @@ROWCOUNT;

    INSERT INTO core.DimWard (WardCode, WardName, WardType, BedCount, AccommodationTariffCode)
    SELECT s.WardCode, s.WardName, s.WardType, s.BedCount, s.AccommodationTariffCode
    FROM   landing.Ward AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.DimWard AS d WHERE d.WardCode = s.WardCode);
    SET @Rows += @@ROWCOUNT;

    -- doctors
    UPDATE d
    SET    DoctorName = s.DoctorName, Speciality = s.Speciality
    FROM   core.DimDoctor AS d
    JOIN   landing.Doctor AS s ON s.DoctorID = d.DoctorID
    WHERE  EXISTS (SELECT s.DoctorName, s.Speciality EXCEPT SELECT d.DoctorName, d.Speciality);
    SET @Rows += @@ROWCOUNT;

    INSERT INTO core.DimDoctor (DoctorID, DoctorName, Speciality)
    SELECT s.DoctorID, s.DoctorName, s.Speciality
    FROM   landing.Doctor AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.DimDoctor AS d WHERE d.DoctorID = s.DoctorID);
    SET @Rows += @@ROWCOUNT;

    -- funders
    UPDATE d
    SET    FunderName = s.FunderName, FunderType = s.FunderType, CoverPct = s.CoverPct
    FROM   core.DimFunder AS d
    JOIN   landing.Funder AS s ON s.FunderCode = d.FunderCode
    WHERE  EXISTS (SELECT s.FunderName, s.FunderType, s.CoverPct
                   EXCEPT
                   SELECT d.FunderName, d.FunderType, d.CoverPct);
    SET @Rows += @@ROWCOUNT;

    INSERT INTO core.DimFunder (FunderCode, FunderName, FunderType, CoverPct)
    SELECT s.FunderCode, s.FunderName, s.FunderType, s.CoverPct
    FROM   landing.Funder AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.DimFunder AS d WHERE d.FunderCode = s.FunderCode);
    SET @Rows += @@ROWCOUNT;

    -- patients
    UPDATE d
    SET    FullName = s.FullName, DateOfBirth = s.DateOfBirth, Gender = s.Gender, City = s.City
    FROM   core.DimPatient AS d
    JOIN   landing.Patient AS s ON s.PatientID = d.PatientID
    WHERE  EXISTS (SELECT s.FullName, s.DateOfBirth, s.Gender, s.City
                   EXCEPT
                   SELECT d.FullName, d.DateOfBirth, d.Gender, d.City);
    SET @Rows += @@ROWCOUNT;

    INSERT INTO core.DimPatient (PatientID, FullName, DateOfBirth, Gender, City)
    SELECT s.PatientID, s.FullName, s.DateOfBirth, s.Gender, s.City
    FROM   landing.Patient AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.DimPatient AS d WHERE d.PatientID = s.PatientID);
    SET @Rows += @@ROWCOUNT;
END;
GO

/* The price list. The file has one row per tariff code per effective date.
   EffectiveTo is not in the file, it is worked out from the next row for the same code. */
CREATE OR ALTER PROCEDURE core.usp_LoadTariffs
    @Rows int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @Rows = 0;

    UPDATE d
    SET    Description = s.Description, Category = s.Category, UnitOfMeasure = s.UnitOfMeasure,
           Rate = s.Rate, IsFunderCovered = s.IsFunderCovered
    FROM   core.DimTariff AS d
    JOIN   landing.Tariff AS s ON s.TariffCode = d.TariffCode AND s.EffectiveFrom = d.EffectiveFrom
    WHERE  EXISTS (SELECT s.Description, s.Category, s.UnitOfMeasure, s.Rate, s.IsFunderCovered
                   EXCEPT
                   SELECT d.Description, d.Category, d.UnitOfMeasure, d.Rate, d.IsFunderCovered);
    SET @Rows += @@ROWCOUNT;

    INSERT INTO core.DimTariff (TariffCode, Description, Category, UnitOfMeasure, Rate,
                                IsFunderCovered, EffectiveFrom, EffectiveTo)
    SELECT s.TariffCode, s.Description, s.Category, s.UnitOfMeasure, s.Rate,
           s.IsFunderCovered, s.EffectiveFrom, '9999-12-31'
    FROM   landing.Tariff AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.DimTariff AS d
                       WHERE d.TariffCode = s.TariffCode AND d.EffectiveFrom = s.EffectiveFrom);
    SET @Rows += @@ROWCOUNT;

    -- a rate runs until the day before the next rate for the same code starts
    WITH Ordered AS (
        SELECT EffectiveTo,
               COALESCE(DATEADD(DAY, -1, LEAD(EffectiveFrom) OVER (PARTITION BY TariffCode ORDER BY EffectiveFrom)),
                        '9999-12-31') AS NewEffectiveTo
        FROM   core.DimTariff
    )
    UPDATE Ordered
    SET    EffectiveTo = NewEffectiveTo
    WHERE  EffectiveTo <> NewEffectiveTo;
END;
GO

/* Admissions. New ones are inserted. Ones that changed (usually because the
   patient has now been discharged) are updated. */
CREATE OR ALTER PROCEDURE core.usp_LoadAdmissions
    @Rows int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @Rows = 0;

    UPDATE f
    SET    WardKey           = w.WardKey,
           DoctorKey         = dr.DoctorKey,
           FunderKey         = fu.FunderKey,
           DischargeDateTime = s.DischargeDateTime,
           DischargeDateKey  = c.DischargeDateKey,
           LengthOfStayDays  = c.LengthOfStayDays,
           AuthorisationNo   = s.AuthorisationNo,
           AdmissionType     = s.AdmissionType,
           DiagnosisGroup    = s.DiagnosisGroup
    FROM   core.FactAdmission AS f
    JOIN   landing.Admission  AS s  ON s.AdmissionID = f.AdmissionID
    JOIN   core.DimWard       AS w  ON w.WardCode    = s.WardCode
    JOIN   core.DimDoctor     AS dr ON dr.DoctorID   = s.DoctorID
    JOIN   core.DimFunder     AS fu ON fu.FunderCode = s.FunderCode
    CROSS APPLY (SELECT CONVERT(int, CONVERT(char(8), s.DischargeDateTime, 112)) AS DischargeDateKey,
                        -- a same-day stay counts as 1 day
                        CASE WHEN s.DischargeDateTime IS NULL THEN NULL
                             WHEN DATEDIFF(DAY, s.AdmitDateTime, s.DischargeDateTime) = 0 THEN 1
                             ELSE DATEDIFF(DAY, s.AdmitDateTime, s.DischargeDateTime) END AS LengthOfStayDays) AS c
    WHERE  EXISTS (SELECT w.WardKey, dr.DoctorKey, fu.FunderKey, s.DischargeDateTime,
                          s.AuthorisationNo, s.AdmissionType, s.DiagnosisGroup
                   EXCEPT
                   SELECT f.WardKey, f.DoctorKey, f.FunderKey, f.DischargeDateTime,
                          f.AuthorisationNo, f.AdmissionType, f.DiagnosisGroup);
    SET @Rows += @@ROWCOUNT;

    INSERT INTO core.FactAdmission (AdmissionID, PatientKey, WardKey, DoctorKey, FunderKey,
                                    AdmitDateKey, DischargeDateKey, AdmitDateTime, DischargeDateTime,
                                    LengthOfStayDays, AuthorisationNo, AdmissionType, DiagnosisGroup)
    SELECT s.AdmissionID, p.PatientKey, w.WardKey, dr.DoctorKey, fu.FunderKey,
           CONVERT(int, CONVERT(char(8), s.AdmitDateTime, 112)),
           CONVERT(int, CONVERT(char(8), s.DischargeDateTime, 112)),
           s.AdmitDateTime, s.DischargeDateTime,
           CASE WHEN s.DischargeDateTime IS NULL THEN NULL
                WHEN DATEDIFF(DAY, s.AdmitDateTime, s.DischargeDateTime) = 0 THEN 1
                ELSE DATEDIFF(DAY, s.AdmitDateTime, s.DischargeDateTime) END,
           s.AuthorisationNo, s.AdmissionType, s.DiagnosisGroup
    FROM   landing.Admission AS s
    JOIN   core.DimPatient   AS p  ON p.PatientID   = s.PatientID
    JOIN   core.DimWard      AS w  ON w.WardCode    = s.WardCode
    JOIN   core.DimDoctor    AS dr ON dr.DoctorID   = s.DoctorID
    JOIN   core.DimFunder    AS fu ON fu.FunderCode = s.FunderCode
    WHERE  NOT EXISTS (SELECT 1 FROM core.FactAdmission AS f WHERE f.AdmissionID = s.AdmissionID);
    SET @Rows += @@ROWCOUNT;
END;
GO

/* Charges - this is where the billing rules are.

   Amount        = Quantity x the tariff rate that was valid on the service date
   FunderAmount  = Amount x the funder's cover %, but only if the tariff is one funders pay for
   PatientAmount = whatever is left

   There are two kinds of charge line:
   1. Captured      - from the charge files (theatre minutes, procedures, pharmacy and so on)
   2. Accommodation - not in any file. One line per night in the ward, worked out from the
                      admission and discharge dates, at the ward's accommodation tariff.     */
CREATE OR ALTER PROCEDURE core.usp_LoadCharges
    @Rows int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @Rows = 0;

    -- 1. captured charges, only the ones not loaded before
    INSERT INTO core.FactCharge (ChargeSource, SourceChargeID, AdmissionKey, ServiceDateKey, TariffKey,
                                 Quantity, Rate, Amount, FunderAmount, PatientAmount)
    SELECT 'Captured', s.ChargeID, a.AdmissionKey,
           CONVERT(int, CONVERT(char(8), s.ServiceDate, 112)),
           t.TariffKey, s.Quantity, t.Rate,
           amt.Amount, split.FunderAmount, amt.Amount - split.FunderAmount
    FROM   landing.Charge     AS s
    JOIN   core.FactAdmission AS a  ON a.AdmissionID = s.AdmissionID
    JOIN   core.DimFunder     AS fu ON fu.FunderKey  = a.FunderKey
    JOIN   core.DimTariff     AS t  ON t.TariffCode  = s.TariffCode
                                   AND s.ServiceDate BETWEEN t.EffectiveFrom AND t.EffectiveTo
    CROSS APPLY (SELECT CAST(ROUND(s.Quantity * t.Rate, 2) AS decimal(12,2)) AS Amount) AS amt
    CROSS APPLY (SELECT CASE WHEN t.IsFunderCovered = 1
                             THEN CAST(ROUND(amt.Amount * fu.CoverPct / 100.0, 2) AS decimal(12,2))
                             ELSE CAST(0 AS decimal(12,2)) END AS FunderAmount) AS split
    WHERE  NOT EXISTS (SELECT 1 FROM core.FactCharge AS f WHERE f.SourceChargeID = s.ChargeID);
    SET @Rows += @@ROWCOUNT;

    -- 2. accommodation. rebuilt from scratch every run because stays change
    --    (a patient who was still in hospital last run may be discharged now)
    DELETE FROM core.FactCharge WHERE ChargeSource = 'Accommodation';

    -- patients still in hospital are charged up to the latest date we have data for
    DECLARE @AsAt date = (SELECT MAX(d)
                          FROM (SELECT MAX(CAST(AdmitDateTime AS date)) FROM core.FactAdmission
                                UNION ALL
                                SELECT MAX(CAST(DischargeDateTime AS date)) FROM core.FactAdmission) AS x (d));

    INSERT INTO core.FactCharge (ChargeSource, SourceChargeID, AdmissionKey, ServiceDateKey, TariffKey,
                                 Quantity, Rate, Amount, FunderAmount, PatientAmount)
    SELECT 'Accommodation', NULL, a.AdmissionKey, d.DateKey, t.TariffKey,
           1, t.Rate, t.Rate, split.FunderAmount, t.Rate - split.FunderAmount
    FROM   core.FactAdmission AS a
    JOIN   core.DimWard       AS w  ON w.WardKey   = a.WardKey
    JOIN   core.DimFunder     AS fu ON fu.FunderKey = a.FunderKey
    CROSS APPLY (SELECT CAST(a.AdmitDateTime AS date) AS AdmitDate,
                        CAST(a.DischargeDateTime AS date) AS DischargeDate) AS s
    -- one row per night: from the admit date up to (not including) the discharge date.
    -- the admit date always counts, so a day case is charged one day.
    JOIN   core.DimDate       AS d  ON d.FullDate >= s.AdmitDate
                                   AND (   (s.DischargeDate IS NULL AND d.FullDate <= @AsAt)
                                        OR (s.DischargeDate IS NOT NULL
                                            AND (d.FullDate < s.DischargeDate OR d.FullDate = s.AdmitDate)))
    -- the rate valid on that night, so a stay over a price increase gets both rates
    JOIN   core.DimTariff     AS t  ON t.TariffCode = w.AccommodationTariffCode
                                   AND d.FullDate BETWEEN t.EffectiveFrom AND t.EffectiveTo
    CROSS APPLY (SELECT CASE WHEN t.IsFunderCovered = 1
                             THEN CAST(ROUND(t.Rate * fu.CoverPct / 100.0, 2) AS decimal(12,2))
                             ELSE CAST(0 AS decimal(12,2)) END AS FunderAmount) AS split;
    SET @Rows += @@ROWCOUNT;
END;
GO

CREATE OR ALTER PROCEDURE core.usp_LoadPayments
    @Rows int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO core.FactPayment (PaymentID, AdmissionKey, PaymentDateKey, PayerType, PaymentMethod, Amount)
    SELECT s.PaymentID, a.AdmissionKey,
           CONVERT(int, CONVERT(char(8), s.PaymentDate, 112)),
           s.PayerType, s.PaymentMethod, s.Amount
    FROM   landing.Payment    AS s
    JOIN   core.FactAdmission AS a ON a.AdmissionID = s.AdmissionID
    WHERE  NOT EXISTS (SELECT 1 FROM core.FactPayment AS f WHERE f.PaymentID = s.PaymentID);
    SET @Rows = @@ROWCOUNT;
END;
GO

/* Main proc - runs all the steps in one transaction and logs the result. */
CREATE OR ALTER PROCEDURE core.usp_RunLoad
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Start datetime2(0) = SYSDATETIME(), @Rows int;
    -- table variables are not rolled back, so the step results survive a failure
    DECLARE @Steps TABLE (StepNo int IDENTITY(1,1), StepName sysname, RowsAffected int);

    BEGIN TRY
        BEGIN TRANSACTION;

        EXEC core.usp_LoadDimensions @Rows = @Rows OUTPUT;
        INSERT INTO @Steps (StepName, RowsAffected) VALUES (N'core.usp_LoadDimensions', @Rows);

        EXEC core.usp_LoadTariffs @Rows = @Rows OUTPUT;
        INSERT INTO @Steps (StepName, RowsAffected) VALUES (N'core.usp_LoadTariffs', @Rows);

        EXEC core.usp_LoadAdmissions @Rows = @Rows OUTPUT;
        INSERT INTO @Steps (StepName, RowsAffected) VALUES (N'core.usp_LoadAdmissions', @Rows);

        EXEC core.usp_LoadCharges @Rows = @Rows OUTPUT;
        INSERT INTO @Steps (StepName, RowsAffected) VALUES (N'core.usp_LoadCharges', @Rows);

        EXEC core.usp_LoadPayments @Rows = @Rows OUTPUT;
        INSERT INTO @Steps (StepName, RowsAffected) VALUES (N'core.usp_LoadPayments', @Rows);

        COMMIT TRANSACTION;

        INSERT INTO audit.LoadLog (StepName, StartTime, EndTime, RowsAffected, LoadStatus)
        SELECT StepName, @Start, SYSDATETIME(), RowsAffected, 'Success'
        FROM   @Steps
        ORDER BY StepNo;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;

        INSERT INTO audit.LoadLog (StepName, StartTime, EndTime, RowsAffected, LoadStatus, ErrorMessage)
        VALUES (N'core.usp_RunLoad', @Start, SYSDATETIME(), 0, 'Failed', ERROR_MESSAGE());

        THROW;   -- so the Python script fails too
    END CATCH;
END;
GO
