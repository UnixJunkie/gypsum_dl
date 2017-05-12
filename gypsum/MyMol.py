import gypsum.Utils as Utils
import sys
import copy
import operator

try:
    from rdkit.Chem import AllChem
    from rdkit import Chem
    from rdkit.Chem.rdchem import BondStereo
except:
    Utils.log("You need to install rdkit and its dependencies.")
    sys.exit(0)

try:
    from molvs import standardize_smiles as ssmiles
except:
    Utils.log("You need to install molvs and its dependencies.")
    sys.exit(0)

class MyConformer:
    """
    A wrapper around a rdkit Conformer object. Allows me to associate extra
    values with conformers.
    """

    def __init__(self, mol, conformer=None):
        """
        Create a MyConformer objects.

        :param MyMol.MyMol mol: The MyMol.MyMol associated with this
                           conformer.

        :param rdkit.Conformer conformer: An optional variable specifying the
                               conformer to use. If not specified, it will
                               create a new conformer.
        """
                
        # Generate the conformer from that mol
        self.mol = copy.deepcopy(mol.rdkit_mol)
        self.mol.RemoveAllConformers()
        self.smiles = mol.smiles()

        if conformer is None:
            # Note that I have confirmed that the below respects chiral.
            params = AllChem.ETKDG()
            
            # The default, but just a sanity check.
            params.enforcechiral = True

            # This sometimes takes a very long time
            AllChem.EmbedMolecule(self.mol, params)

            # On very rare occasions, the new conformer generating algorithm
            # fails. For example, COC(=O)c1cc(C)nc2c(C)cc3[nH]c4ccccc4c3c12 .
            # In this case, the old one still works. So if no coordinates are
            # assigned, try that one.
            if self.mol.GetNumConformers() == 0:
                AllChem.EmbedMolecule(self.mol)
            # On rare occasions, both methods fail. For example,
            # O=c1cccc2[C@H]3C[NH2+]C[C@@H](C3)Cn21
            # Another example: COc1cccc2c1[C@H](CO)[N@H+]1[C@@H](C#N)[C@@H]3C[C@@H](C(=O)[O-])[C@H]([C@H]1C2)[N@H+]3C
            if self.mol.GetNumConformers() == 0:
                self.mol = False
        else:
            conformer.SetId(0)
            self.mol.AddConformer(conformer, assignId=True)

        if self.mol is not False:
            ff = AllChem.UFFGetMoleculeForceField(self.mol)
            self.minimized = False
            self.energy = ff.CalcEnergy()
            self.ids_hvy_atms = [a.GetIdx() for a in self.mol.GetAtoms()
                                       if a.GetAtomicNum() != 1]

    def conformer(self, conf=None):
        """
        Get or set the conformer.

        :param rdkit.Conformer conf: An optional variable specifying the
                               conformer to set. If not specified, this
                               function acts as a get for the conformer.

        :returns: an rdkit.Conformer object, if conf is not specified.
        :rtype: :class:`str` ???
        """
        
        if conf is None:
            return self.mol.GetConformers()[0]
        else:
            self.mol.RemoveAllConformers()
            self.mol.AddConformer(conf)

    def minimize(self):
        """
        Minimize (optimize) the geometry of the current conformer.
        """

        if self.minimized == True:
            return

        ff = AllChem.UFFGetMoleculeForceField(self.mol)
        ff.Minimize()
        self.energy = ff.CalcEnergy()
        self.minimized = True
    
    def align_to_me(self, other_conf):
        """
        Another another conformer to this one.

        :param MyConformer other_conf: The other conformer to align.

        :returns: the aligned MyConformer object.
        :rtype: :class:`str` ???
        """

        # Add the conformer of the other MyConformer object.
        self.mol.AddConformer(other_conf.conformer(), assignId=True)

        # Align them
        AllChem.AlignMolConformers(self.mol, atomIds = self.ids_hvy_atms)

        # Reset the conformer of the other MyConformer object.
        last_conf = self.mol.GetConformers()[-1]
        other_conf.conformer(last_conf)
        
        # Remove the added conformer
        self.mol.RemoveConformer(last_conf.GetId())

        # Return that other object.
        return other_conf

    def MolToMolBlock(self):
        """
        Prints out the first 500 letters of the molblock version of this
        conformer.
        """

        mol_copy = copy.deepcopy(self.mol_copy)  # Use it as a template.
        mol_copy.RemoveAllConformers()
        mol_copy.AddConformer(self.conformer)
        print(Chem.MolToMolBlock(mol_copy)[:500])
    
    def rmsd_to_me(self, other_conf):
        """
        Calculate the rms distance between this conformer and another one.

        :param MyConformer other_conf: The other conformer to align.

        :returns: the rmsd, a float.
        :rtype: :class:`float` ???
        """

        # Make a new molecule
        amol = Chem.MolFromSmiles(self.smiles)
        amol = Chem.AddHs(amol)

        # Add the conformer of the other MyConformer object.
        amol.AddConformer(self.conformer(), assignId=True)
        amol.AddConformer(other_conf.conformer(), assignId=True)
        
        # Get the two confs
        first_conf = amol.GetConformers()[0]
        last_conf = amol.GetConformers()[-1]

        # Return the RMSD
        amol = Chem.RemoveHs(amol)
        rmsd = AllChem.GetConformerRMS(
            amol, first_conf.GetId(), last_conf.GetId(), prealigned = True
        )

        return rmsd


class MyMol:
    """
    A class that wraps around a rdkit.Mol object.
    """

    def __init__(self, smiles, name=""):
        """
        Initialize the MyMol object.

        :param [str or rdkit.Mol] smiles: The object (smiles or rdkit.Mol)
                                  on which to build this class.

        :param str name: An optional string, the name of this molecule.
        """

        if isinstance(smiles, str):
            self.rdkit_mol = ""
            self.can_smi = ""
        else:
            # So it's an rdkit mol object.
            self.rdkit_mol = smiles  # No need to regenerate this

            # Get the smiles too.
            try:
                smiles = Chem.MolToSmiles(
                    self.rdkit_mol, isomericSmiles=True, canonical=True
                )

                # In this case you know it's cannonical.
                self.can_smi = smiles
            except:
                # Sometimes this conversion just can't happen. Happened once
                # with this beast, for example:
                # CC(=O)NC1=CC(=C=[N+]([O-])O)C=C1O
                self.can_smi = False
                Utils.log(
                    "\tERROR: Could not generate one of the structures " +
                    "for (" + name + ")."
                )

        self.can_smi_noh = ""
        self.orig_smi = smiles

        # Default assumption is that they are the same.
        self.orig_smi_deslt = smiles
        self.name = name
        self.conformers = []
        self.nonaro_ring_atom_idx = ""
        self.chiral_cntrs_only_assigned = ""
        self.chiral_cntrs_include_unasignd = ""
        self.crzy_substruct = ""
        self.enrgy = {}  # different energies for different conformers.
        self.minimized_enrgy = {}
        self.contnr_idx = ""
        self.frgs = ""
        self.stdrd_smiles = ""
        self.mol_props = {}
        self.idxs_low_energy_confs_no_opt = {}
        self.idxs_of_confs_to_min = set([])
        self.genealogy = []  # Keep track of how the molecule came to be.

        self.makeMolFromSmiles()
    
    def standardize_smiles(self):
        """
        Standardize the smiles string if you can.
        """
        
        if self.stdrd_smiles != "":
            return self.stdrd_smiles

        try:
            self.stdrd_smiles = ssmiles(self.smiles())
        except:
            Utils.log(
                "\tCould not standardize " + self.smiles(True) + ". Skipping."
            )
            self.stdrd_smiles = self.smiles()

        return self.stdrd_smiles

    def __hash__(self):
        can_smi = self.smiles()
        
        # So it hashes based on the cannonical smiles.
        return hash(can_smi)
    
    def __eq__(self, other):
        return self.__hash__() == other.__hash__()
    
    def GetNumConformers(self):
        """
        Get the number of conformers associated with this object.

        :returns: int, the number of conformers.
        :rtype: :class:`int` ???
        """
        
        return len(self.conformers)

    def makeMolFromSmiles(self):
        """
        Construct a rdkit.mol for this object, since you likely only received
        the smiles.

        :returns: returns the rdkit.mol object, those it's also stored in
                  self.rdkit_mol
        :rtype: :class:`str` ???
        """
        
        # Get the mol if it's already been calculated, otherwise calculate it
        # and get it.
        # Note this is mol without any geometry.
        if self.rdkit_mol != "":
            return self.rdkit_mol

        #standardized_smiles = self.standardize_smiles()

        # So make the mol
        # Stuff added here from https://github.com/rdkit/rdkit/pull/809 to fix
        # a bug.
        a = 0
        for k,v in Chem.rdmolops.SanitizeFlags.values.items():
            if v not in [Chem.rdmolops.SanitizeFlags.SANITIZE_CLEANUP,
                        Chem.rdmolops.SanitizeFlags.SANITIZE_ALL]:
                a |= v

        m = Chem.MolFromSmiles(self.orig_smi_deslt, sanitize=False)

        try:
            Chem.SanitizeMol(m, sanitizeOps=a)
        except:
            # You might consider returning None. Let's see if we get errors...
            self.rdkit_mol = None
            return None

        self.rdkit_mol = m
        return m

    def makeMol3D(self):
        """
        The the associated rdkit.mol object 3D by adding a conformer. This
        also adds hydrogen atoms to the associated rdkit.mol object.
        """
        
        # Set the first 3D conformer
        if self.GetNumConformers() > 0:
            # It's already beendone.
            return

        # Add hydrogens
        self.rdkit_mol = Chem.AddHs(self.rdkit_mol)

        # Add a conformer
        # No minimization. Rmsd cutoff doesn't matter.
        self.add_conformers(1, 1e60, False)

    def smiles(self, noh=False):
        """
        Get the canonical smiles string associated with this object.

        :param bool noh: Whether or not hydrogen atoms should be included in
                    the canonical smiles string.

        :returns: the canonical smiles string.
        :rtype: :class:`str` ???
        """
        
        # This is really for the cannonical smiles, not the input smiles.
        # It is also the desaulted smiles.

        # See if it's already been calculated.
        if noh == False:
            if self.can_smi != "":
                return self.can_smi
        else:
            if self.can_smi_noh != "":
                return self.can_smi_noh

            # So remove hydrogens. Note that this assumes you will have called
            # this function previously with noh = False
            amol = copy.copy(self.rdkit_mol)
            amol = Chem.RemoveHs(amol)
            self.can_smi_noh = Chem.MolToSmiles(
                amol, isomericSmiles=True, canonical=True
            )
            return self.can_smi_noh
        
        try:
            can_smi = Chem.MolToSmiles(
                self.rdkit_mol, isomericSmiles=True, canonical=True
            )
        except:
            # Sometimes this conversion just can't happen. Happened once with
            # this beast, for example: CC(=O)NC1=CC(=C=[N+]([O-])O)C=C1O
            Utils.log("Warning: Couldn't put " + self.orig_smi + " (" +
                      self.name + ") in canonical form. Got this error: " +
                      str(sys.exc_info()[0]) + ". This molecule will be " +
                      "discarded.")
            self.can_smi = None
            return None

        self.can_smi = can_smi
        return can_smi

    def m_num_nonaro_rngs(self):
        """
        Identifies which rings in a given molecule are nonaromatic, if any.

        :returns: A [[int, int, int]]. A list of lists, where each inner list
                  is a list of the atom indecies of the members of a
                  non-aromatic ring.
        :rtype: :class:`str` ???
        """

        if self.nonaro_ring_atom_idx != "":
            return self.nonaro_ring_atom_idx

        if self.rdkit_mol is None:
            return []

        # Get the rings
        ssr = Chem.GetSymmSSSR(self.rdkit_mol)
        ring_indecies = [list(ssr[i]) for i in range(len(ssr))]
        
        # Are the atoms in any of those rings nonaromatic?
        nonaro_rngs = []
        for rng_indx_set in ring_indecies:
            for atm_idx in rng_indx_set:
                if self.rdkit_mol.GetAtomWithIdx(atm_idx).GetIsAromatic() == False:
                    # One of the ring atoms is not aromatic!
                    nonaro_rngs.append(rng_indx_set)
                    break
        self.nonaro_ring_atom_idx = nonaro_rngs
        return nonaro_rngs

    def chiral_cntrs_w_unasignd(self):
        """
        Get the chiral centers that haven't been assigned.

        :returns: the chiral centers.
        :rtype: :class:`str` ???
        """
        
        if self.chiral_cntrs_include_unasignd != "":
            return self.chiral_cntrs_include_unasignd

        if self.rdkit_mol is None:
            return []
                
        ccs = Chem.FindMolChiralCenters(self.rdkit_mol, includeUnassigned=True)
        self.chiral_cntrs_include_unasignd = ccs
        return ccs

    def chiral_cntrs_only_asignd(self):
        """
        Get the chiral centers that have been assigned.

        :returns: the chiral centers.
        :rtype: :class:`str` ???
        """
        
        if self.chiral_cntrs_only_assigned != "":
            return self.chiral_cntrs_only_assigned
        
        if self.rdkit_mol is None:
            return []
        
        ccs = Chem.FindMolChiralCenters(self.rdkit_mol, includeUnassigned=False)
        self.chiral_cntrs_only_assigned = ccs
        return ccs

    def get_double_bonds_without_stereochemistry(self):
        """
        Get the double bonds that don't have specified stereochemistry.

        :returns: the unasignd double bonds.
        :rtype: :class:`str` ???
        """
        
        if self.rdkit_mol is None:
            return []

        unasignd = []
        for b in self.rdkit_mol.GetBonds():
            if (b.GetBondTypeAsDouble() == 2 and 
                b.GetStereo() is BondStereo.STEREONONE):

                unasignd.append(b.GetIdx())

        return unasignd

    def crzy_substruc(self):
        """
        Removes molecules with improbable substuctures, likely generated from
        the tautomerization process.

        :returns: boolean, whether or not there are crazy substructures.
        :rtype: :class:`bool`
        """

        if self.crzy_substruct != "":
            return self.crzy_substruct

        # These are substrutures that can't be easily corrected using
        # fix_common_errors() below.
        #, "[C+]", "[C-]", "[c+]", "[c-]", "[n-]", "[N-]"] # , 
        # "[*@@H]1(~[*][*]~2)~[*]~[*]~[*@@H]2~[*]~[*]~1",
        # "[*@@H]1~2~*~*~[*@@H](~*~*2)~*1",
        # "[*@@H]1~2~*~*~*~[*@@H](~*~*2)~*1",
        # "[*@@H]1~2~*~*~*~*~[*@@H](~*~*2)~*1",
        # "[*@@H]1~2~*~[*@@H](~*~*2)~*1", "[*@@H]~1~2~*~*~*~[*@H]1O2",
        # "[*@@H]~1~2~*~*~*~*~[*@H]1O2"]
        
        # Note that C(O)=N, C and N mean they are aliphatic. Does not match
        # c(O)n, when aromatic. So this form is acceptable if in aromatic
        # structure.
        prohibited_substructures = ["O(=*)-*", "C(O)=N"]

        for s in prohibited_substructures:
            # First just match strings... could be faster, but not 100%
            # accurate.
            if s in self.orig_smi:
                self.crzy_substruct = True
                return True

            if s in self.orig_smi_deslt:
                self.crzy_substruct = True
                return True

            if s in self.can_smi:
                self.crzy_substruct = True
                return True

        # Now do actual substructure matching
        for s in prohibited_substructures:
            pattrn = Chem.MolFromSmarts(s)
            if self.rdkit_mol.HasSubstructMatch(pattrn):
                # Utils.log("\tRemoving a molecule because it has an odd
                # substructure: " + s)
                self.crzy_substruct = True
                return True
        
        # Now certin patterns that are more complex.
        
        self.crzy_substruct = False
        return False

    def fix_common_errors(self):
        """
        Try to fix common structural erors.
        """
        
        mol = self.rdkit_mol

        orig_can_smi = True
        new_can_smi = False

        tt = self.smiles()

        while orig_can_smi != new_can_smi:
            orig_can_smi = self.smiles()

            if mol is not None:

                # inappropriate carbocations
                if "[C+]" in orig_can_smi:
                    mol = AllChem.ReplaceSubstructs(
                        mol,
                        Chem.MolFromSmarts('[$([C+](=*)(-*)-*)]'),
                        Chem.MolFromSmiles('C')
                    )[0]
                
                # Inappropriate modifications to carboxylic acids
                smrts = Chem.MolFromSmarts("C([O-])O")
                if self.rdkit_mol.HasSubstructMatch(smrts):
                    rxn = AllChem.ReactionFromSmarts(
                        '[CH1:1](-[OH1:2])-[OX1-:3]>>[C:1](=[O:2])[O-:3]'
                    )
                    r = rxn.RunReactants([mol])
                    if len(r) > 0:
                        mol = r[0][0]

                # N+ bonded to only three atoms does not have a positive
                # charge.
                smrts = Chem.MolFromSmarts("[NX3+]")
                if self.rdkit_mol.HasSubstructMatch(smrts):
                    rxn = AllChem.ReactionFromSmarts('[NX3+:1]>>[N:1]')   
                    r = rxn.RunReactants([mol])
                    if len(r) > 0:
                        mol = r[0][0]

                # In practie, you never get to the below anyway, because you
                # can't convert to mol. if
                self.rdkit_mol = mol
                self.can_smi = ""  # Force it to recalculate canonical smiles
            else:
                return None  # It's invalid somehow

            new_can_smi = self.smiles()

    def get_frags_of_orig_smi(self):
        """
        Divide the current molecule into fragments.

        :returns: a list of the fragments, as rdkit.Mol objects.
        :rtype: :class:`str` ???
        """
        
        if self.frgs != "":
            return self.frgs

        if not "." in self.orig_smi:
            # There are no fragments. Just return this object.
            self.frgs = [self]
            return [self]
        
        frags = Chem.GetMolFrags(self.rdkit_mol, asMols=True)
        self.frgs = frags
        return frags
    
    def inherit_contnr_props(self, other):
        """
        Copies a few key properties from a different MyMol.MyMol object to
        this one. In my view this function is under-used.

        :param MyMol.MyMol other: The other MyMol.MyMol object to copy these
                           properties to.
        """
        
        # other can be a contnr or MyMol.MyMol object.
        # these are properties that should be the same for every MyMol.MyMol
        # object in this MolContainer
        self.contnr_idx = other.contnr_idx
        self.orig_smi = other.orig_smi
        self.orig_smi_deslt = other.orig_smi_deslt  # initial assumption
        self.name = other.name

    def copy(self):
        """
        Make a copy of this MyMol.MyMol object.

        :returns: a copy of this object.
        :rtype: :class:`MyMol.MyMol` ???
        """
        
        return copy.deepcopy(self)
    
    def GetAtomWithIdx(self, idx):
        """
        Get the atom with the specified index.

        :param int idx: The index of the atom.

        :returns: the rdkit atom object.
        :rtype: :class:`str` ???
        """
        
        # I think this one should be cached.
        return self.rdkit_mol.GetAtomWithIdx(idx)
    
    def GetBondWithIdx(self, idx):
        """
        Get the bond with the specified index.

        :param int idx: The index of the bond.

        :returns: the rdkit bond object.
        :rtype: :class:`str` ???
        """
        
        return self.rdkit_mol.GetBondWithIdx(idx)
    
    def AssignStereochemistry(self):
        """
        Assign stereochemistry to this molecule.
        """
        # Required to actually set it.
        Chem.AssignStereochemistry(self.rdkit_mol, force=True)
    
    def setRDKitMolProp(self, key, val):
        """
        Set a molecular property.

        :param str key: The name of the molecular property.

        :param str val: The value of that property.
        """
        
        val = str(val)
        self.rdkit_mol.SetProp(key, val)
        self.rdkit_mol.SetProp(key, val)
        
        try:
            self.rdkit_mol.SetProp(key, val)
        except:
            pass
    
    def setAllRDKitMolProps(self):
        """
        Set all the stored molecular properties.
        """
        
        self.setRDKitMolProp("SMILES", self.smiles(True))
        #self.setRDKitMolProp("SOURCE_SMILES", self.orig_smi)
        for prop in self.mol_props.keys():
            self.setRDKitMolProp(prop, self.mol_props[prop])
        genealogy = "\n".join(self.genealogy)
        self.setRDKitMolProp("Genealogy", genealogy)
        self.setRDKitMolProp("_Name", self.name)
        
    def add_conformers(self, num, rmsd_cutoff=0.1, minimize=True):
        """
        Add conformers to this molecule.

        :param int num: The total number of conformers to generate, including
                   ones that have been generated previously.

        :param float rmsd_cutoff: Don't keep conformers that come within this
                     rms distance of other conformers.

        :param bool minimize: Whether or not to minimize the geometry of all
                     these conformers. Defaults to True.
        """
        
        # First, do you need to add new conformers?
        num_new_confs = max(0, num - len(self.conformers))
        for i in range(num_new_confs):
            new_conf = MyConformer(self)
            if new_conf.mol is not False:
                self.conformers.append(new_conf)

        # Are the current ones minimized if necessary?
        if minimize == True:
            for conf in self.conformers:
                conf.minimize()
        
        # Automatically sort by the energy
        self.conformers.sort(key=operator.attrgetter('energy'))

        self.eliminate_structurally_similar_conformers(rmsd_cutoff)
    
    def eliminate_structurally_similar_conformers(self, rmsd_cutoff=0.1):
        # Eliminate redundant ones.
        for i1 in range(0, len(self.conformers) - 1):
            if self.conformers[i1] is not None:
                for i2 in range(i1 + 1, len(self.conformers)):
                    if self.conformers[i2] is not None:
                        # Align them
                        self.conformers[i2] = self.conformers[i1].align_to_me(
                            self.conformers[i2]
                        )

                        # Calculate the rmsd
                        rmsd = self.conformers[i1].rmsd_to_me(
                            self.conformers[i2]
                        )

                        # Replace the second one with None if it's too similar
                        # to the first.
                        if rmsd <= rmsd_cutoff:
                            self.conformers[i2] = None

        # Remove all the None entries.
        while None in self.conformers:
            self.conformers.remove(None)

        # what remains are only the distinct conformers.

    # def carb_hyd_cnt_for_non_acidic_carbons(self):
    def carb_hyd_cnt(self):
        if self.rdkit_mol is None:
            return 0

        total_hydrogens_counted = 0
        for atom in self.rdkit_mol.GetAtoms():
            if atom.GetSymbol() == "C":
                # atom_idx = atom.GetIdx()
                # if atom_idx not in carbons_alpha:
                num_Hs = atom.GetNumImplicitHs() + atom.GetNumExplicitHs()
                total_hydrogens_counted = total_hydrogens_counted + num_Hs

        return total_hydrogens_counted
    
    def load_conformations_into_mol_3d(self):
        """
        Load the conformers stored as MyConformers objects (in
        self.conformers) into the rdkit Mol object.
        """
        
        self.rdkit_mol.RemoveAllConformers()
        for conformer in self.conformers:
            self.rdkit_mol.AddConformer(conformer.conformer())
